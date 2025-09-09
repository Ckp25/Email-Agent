import os
from imapclient import IMAPClient
import email
from email.header import decode_header
from datetime import datetime, timedelta
import time
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional
from logger_config import get_logger, log_email_operation, log_batch_start, log_batch_complete, log_performance
from config_loader import config

# Initialize logger for this module
logger = get_logger("mail_reader")


class MailProvider(ABC):
    """Abstract base class for mail providers"""
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to mail provider.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Close connection to mail provider.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
    
    @abstractmethod
    def fetch_unseen_emails(self) -> List[Tuple[str, str, str, int, str]]:
        """
        Fetch all unseen emails without marking them as processed.
        
        Returns:
            List of tuples containing (sender, subject, body, uid, thread_id)
        """
        pass
    
    @abstractmethod
    def fetch_unseen_emails_and_mark_processed(self) -> List[Tuple[str, str, str, int, str]]:
        """
        Fetch all unseen emails and immediately mark them as processed.
        
        Returns:
            List of tuples containing (sender, subject, body, uid, thread_id)
        """
        pass
    
    @abstractmethod
    def mark_email_as_processed(self, uid: int) -> bool:
        """
        Mark a specific email as processed to prevent reprocessing.
        
        Args:
            uid: Email unique identifier
            
        Returns:
            bool: True if marking successful, False otherwise
        """
        pass


class GmailProvider(MailProvider):
    """Gmail IMAP provider implementation"""
    
    def __init__(self):
        try:
            self.email_address = config.email_address
            self.password = config.email_password
            self.imap_server = config.imap_server
            self.imap_port = config.imap_port
            self.label_name = config.label_name
            self.search_days_back = config.search_days_back
            
            logger.info(f"Gmail provider initialized for account: {self.email_address}")
            logger.debug(f"Using IMAP server: {self.imap_server}:{self.imap_port}")
            logger.debug(f"Gmail label: {self.label_name}")
            logger.debug(f"Search days back: {self.search_days_back}")
            
            self.server = None
            
        except Exception as e:
            logger.critical(f"Error initializing Gmail provider: {e}")
            raise
    
    def connect(self) -> bool:
        """Establish IMAP connection to Gmail"""
        try:
            logger.debug(f"Connecting to Gmail IMAP server: {self.imap_server}")
            
            self.server = IMAPClient(self.imap_server)
            logger.debug("Attempting IMAP login")
            self.server.login(self.email_address, self.password)
            logger.info("Successfully connected and authenticated to Gmail IMAP server")
            
            logger.debug("Selecting INBOX folder")
            self.server.select_folder("INBOX", readonly=False)
            logger.debug("Successfully selected INBOX folder")
            
            # Create AI processing label if it doesn't exist
            if not self._create_ai_label():
                logger.warning("Failed to create/verify AI processing label, continuing anyway")
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to Gmail: {e}")
            self.server = None
            return False
    
    def disconnect(self) -> bool:
        """Close IMAP connection"""
        try:
            if self.server:
                self.server.logout()
                logger.debug("Gmail IMAP connection closed")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from Gmail: {e}")
            return False
        finally:
            self.server = None
    
    def _create_ai_label(self) -> bool:
        """Creates the AI processing label if it doesn't exist"""
        try:
            logger.debug(f"Checking for Gmail label: {self.label_name}")
            
            # List existing labels
            existing_labels = self.server.list_folders()
            label_names = [label[2] for label in existing_labels]
            
            if self.label_name not in label_names:
                logger.info(f"Creating Gmail label: {self.label_name}")
                self.server.create_folder(self.label_name)
                logger.info(f"Successfully created Gmail label: {self.label_name}")
            else:
                logger.debug(f"Gmail label already exists: {self.label_name}")
                
            return True
            
        except Exception as e:
            logger.error(f"Error creating/checking Gmail label {self.label_name}: {e}")
            return False
    
    def _clean_subject(self, raw_subject: str) -> str:
        """Clean and decode email subject line"""
        try:
            parts = decode_header(raw_subject)
            subject, encoding = parts[0]
            if isinstance(subject, bytes):
                decoded = subject.decode(encoding or "utf-8", errors="ignore")
                logger.debug(f"Decoded subject from {encoding or 'utf-8'}: {decoded[:50]}...")
                return decoded
            return subject
        except Exception as e:
            logger.error(f"Error decoding subject '{raw_subject}': {e}")
            return raw_subject
    
    def _search_for_emails(self) -> List[int]:
        """Search for unprocessed emails using Gmail-specific criteria"""
        since_date = (datetime.now() - timedelta(days=self.search_days_back)).strftime('%d-%b-%Y')
        logger.debug(f"Searching for emails since: {since_date}")
        
        uids = []
        search_attempts = [
            ('UNSEEN NOT KEYWORD "AI_PROCESSED"', "unprocessed unseen messages"),
            (f'UNSEEN SINCE {since_date}', f"unseen messages since {since_date}"),
            ('UNSEEN', "all unseen messages")
        ]
        
        for i, (criteria, description) in enumerate(search_attempts, 1):
            try:
                logger.debug(f"Search attempt {i}/3: {description}")
                logger.debug(f"Search criteria: {criteria}")
                
                uids = self.server.search(criteria)
                logger.info(f"Search attempt {i} found {len(uids)} emails using: {description}")
                
                if uids:  # Stop if we found emails
                    break
                    
            except Exception as e:
                logger.warning(f"Search attempt {i} failed with criteria '{criteria}': {e}")
                continue
        
        return uids
    
    def _fetch_and_parse_emails(self, uids: List[int]) -> List[Tuple[str, str, str, int, str]]:
        """Fetch and parse email data from Gmail"""
        if not uids:
            return []
        
        logger.debug("Fetching email data (RFC822, INTERNALDATE, X-GM-THRID)")
        response = self.server.fetch(uids, ["RFC822", "INTERNALDATE", "X-GM-THRID"])
        
        if not response:
            logger.warning("IMAP fetch returned no data despite having UIDs")
            return []
        
        logger.debug(f"Successfully fetched data for {len(response)} emails")
        
        emails_with_dates = []
        processed_count = 0
        error_count = 0
        
        log_batch_start(logger, "email parsing", len(response))
        
        for uid, data in response.items():
            try:
                logger.debug(f"Processing email UID {uid}")
                
                raw_msg = data[b"RFC822"]
                msg_date = data[b"INTERNALDATE"]
                
                # Handle Gmail thread ID
                thread_id_raw = data.get(b"X-GM-THRID")
                if thread_id_raw:
                    if isinstance(thread_id_raw, bytes):
                        thread_id = thread_id_raw.decode()
                    else:
                        thread_id = str(thread_id_raw)
                    logger.debug(f"UID {uid} Gmail thread ID: {thread_id}")
                else:
                    thread_id = str(uid)
                    logger.debug(f"UID {uid} no Gmail thread ID found, using UID as thread ID")
                
                if not isinstance(raw_msg, bytes):
                    logger.error(f"UID {uid}: Expected bytes for RFC822, got {type(raw_msg)}")
                    error_count += 1
                    continue
                    
                msg = email.message_from_bytes(raw_msg)
                
                # Parse headers
                from_addr = msg.get("From", "")
                subject = self._clean_subject(msg.get("Subject", ""))
                
                logger.debug(f"UID {uid}: From={from_addr}, Subject={subject[:50]}...")
                
                # Extract plain-text body
                body = self._extract_body(msg, uid)
                
                if not body.strip():
                    logger.warning(f"UID {uid}: No plain text body found")
                
                # Store email data with date for sorting
                email_data = (from_addr, subject, body.strip(), uid, thread_id)
                emails_with_dates.append({
                    'date': msg_date,
                    'data': email_data
                })
                
                processed_count += 1
                logger.debug(f"UID {uid}: Successfully processed and queued for sorting")
                
            except Exception as e:
                logger.error(f"UID {uid}: Error processing email: {e}")
                error_count += 1
                continue
        
        log_batch_complete(logger, "email parsing", processed_count, error_count)
        
        if not emails_with_dates:
            logger.warning("No emails successfully processed")
            return []
        
        # Sort by date (oldest first) and return just the email data
        logger.debug("Sorting emails by date (oldest first)")
        emails_with_dates.sort(key=lambda x: x['date'])
        
        return [email_data['data'] for email_data in emails_with_dates]
    
    def _extract_body(self, msg, uid: int) -> str:
        """Extract plain text body from email message"""
        body = ""
        if msg.is_multipart():
            logger.debug(f"UID {uid}: Processing multipart message")
            for part in msg.walk():
                if part.get_content_type() == "text/plain" and not part.get_content_disposition():
                    try:
                        payload = part.get_payload(decode=True)
                        if isinstance(payload, bytes):
                            body = payload.decode("utf-8", errors="ignore")
                            logger.debug(f"UID {uid}: Extracted plain text body ({len(body)} chars)")
                        break
                    except Exception as e:
                        logger.error(f"UID {uid}: Error decoding message part: {e}")
                        continue
        else:
            logger.debug(f"UID {uid}: Processing single-part message")
            try:
                payload = msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body = payload.decode("utf-8", errors="ignore")
                    logger.debug(f"UID {uid}: Extracted body ({len(body)} chars)")
            except Exception as e:
                logger.error(f"UID {uid}: Error decoding message: {e}")
                body = ""
        
        return body
    
    def mark_email_as_processed(self, uid: int) -> bool:
        """Mark a specific email as processed using Gmail labels"""
        try:
            logger.debug(f"Marking email UID {uid} with Gmail label: {self.label_name}")
            self.server.add_gmail_labels([uid], [self.label_name])
            logger.debug(f"Successfully marked email UID {uid} as processed")
            return True
        except Exception as e:
            logger.error(f"Error marking email UID {uid} as processed: {e}")
            return False
    
    def fetch_unseen_emails(self) -> List[Tuple[str, str, str, int, str]]:
        """Fetch all unseen emails without marking them as processed"""
        start_time = time.time()
        logger.info("Starting to fetch all unseen emails from Gmail")
        
        try:
            if not self.connect():
                logger.error("Failed to connect to Gmail")
                return []
            
            uids = self._search_for_emails()
            if not uids:
                logger.info("No unseen emails found")
                return []
            
            logger.info(f"Found {len(uids)} unseen emails to process: {uids}")
            
            result = self._fetch_and_parse_emails(uids)
            
            duration = time.time() - start_time
            log_performance(logger, "Gmail fetch_unseen_emails", duration, len(result))
            log_email_operation(logger, "fetched", len(result), f"from {len(uids)} total unseen")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Critical error accessing Gmail after {duration:.2f}s: {e}")
            return []
        finally:
            self.disconnect()
    
    def fetch_unseen_emails_and_mark_processed(self) -> List[Tuple[str, str, str, int, str]]:
        """Fetch all unseen emails and immediately mark them as processed"""
        start_time = time.time()
        logger.info("Starting to fetch and mark unseen emails as processed from Gmail")
        
        try:
            if not self.connect():
                logger.error("Failed to connect to Gmail")
                return []
            
            uids = self._search_for_emails()
            if not uids:
                logger.info("No unprocessed unseen emails found")
                return []
            
            logger.info(f"Found {len(uids)} unprocessed emails to fetch and mark: {uids}")
            
            result = self._fetch_and_parse_emails(uids)
            
            # Mark all successfully processed emails as processed
            processed_uids = [email[3] for email in result]  # Extract UIDs from result
            if processed_uids:
                try:
                    logger.info(f"Marking {len(processed_uids)} emails as processed")
                    self.server.add_gmail_labels(processed_uids, [self.label_name])
                    logger.info(f"Successfully marked {len(processed_uids)} emails as processed")
                except Exception as e:
                    logger.error(f"Error marking emails as processed: {e}")
                    logger.warning("Emails were processed but not marked - may be reprocessed on next run")
            
            duration = time.time() - start_time
            log_performance(logger, "Gmail fetch_and_mark_emails", duration, len(result))
            log_email_operation(logger, "fetched and marked", len(result), f"from {len(uids)} total unseen")
            
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Critical error accessing Gmail after {duration:.2f}s: {e}")
            return []
        finally:
            self.disconnect()


class MockMailProvider(MailProvider):
    """Mock mail provider for testing purposes"""
    
    def __init__(self):
        logger.info("Mock mail provider initialized")
        self.is_connected = False
        self.processed_uids = set()
        self.call_count = 0
        
        # Generate some realistic test emails
        self.test_emails = [
            ("customer@example.com", "Product Inquiry", "Hi, I'm interested in your products. Can you tell me more about pricing?", 1001, "thread_001"),
            ("support@testcompany.com", "Website Issue", "I'm having trouble logging into your website. Can you help?", 1002, "thread_002"),
            ("john.doe@business.net", "Partnership Opportunity", "We'd like to discuss a potential partnership with your company.", 1003, "thread_003"),
            ("feedback@customer.org", "Great Service", "Just wanted to say thanks for the excellent customer service!", 1004, "thread_004"),
            ("billing@vendor.com", "Invoice Question", "I have a question about invoice #12345. Can you clarify the charges?", 1005, "thread_005"),
        ]
        
        logger.debug(f"Mock provider created with {len(self.test_emails)} test emails")
    
    def connect(self) -> bool:
        """Simulate connecting to mail server"""
        logger.debug("Mock provider: Simulating connection")
        time.sleep(0.1)  # Simulate connection time
        self.is_connected = True
        logger.info("Mock mail provider connected successfully")
        return True
    
    def disconnect(self) -> bool:
        """Simulate disconnecting from mail server"""
        logger.debug("Mock provider: Simulating disconnection")
        self.is_connected = False
        logger.debug("Mock mail provider disconnected")
        return True
    
    def mark_email_as_processed(self, uid: int) -> bool:
        """Mark email as processed in memory"""
        logger.debug(f"Mock provider: Marking UID {uid} as processed")
        self.processed_uids.add(uid)
        return True
    
    def fetch_unseen_emails(self) -> List[Tuple[str, str, str, int, str]]:
        """Return mock emails that haven't been marked as processed"""
        start_time = time.time()
        logger.info("Mock provider: Fetching unseen emails")
        
        if not self.is_connected:
            if not self.connect():
                return []
        
        # Simulate some processing time
        time.sleep(0.2)
        
        # Return emails that haven't been processed yet
        unseen_emails = [email for email in self.test_emails if email[3] not in self.processed_uids]
        
        self.call_count += 1
        
        duration = time.time() - start_time
        logger.info(f"Mock provider: Found {len(unseen_emails)} unseen emails")
        log_performance(logger, "Mock fetch_unseen_emails", duration, len(unseen_emails))
        
        self.disconnect()
        return unseen_emails
    
    def fetch_unseen_emails_and_mark_processed(self) -> List[Tuple[str, str, str, int, str]]:
        """Return mock emails and mark them as processed"""
        start_time = time.time()
        logger.info("Mock provider: Fetching and marking unseen emails as processed")
        
        if not self.is_connected:
            if not self.connect():
                return []
        
        # Simulate some processing time
        time.sleep(0.3)
        
        # Return emails that haven't been processed yet
        unseen_emails = [email for email in self.test_emails if email[3] not in self.processed_uids]
        
        # Mark them as processed
        for email in unseen_emails:
            self.processed_uids.add(email[3])
        
        self.call_count += 1
        
        duration = time.time() - start_time
        logger.info(f"Mock provider: Fetched and marked {len(unseen_emails)} emails as processed")
        log_performance(logger, "Mock fetch_and_mark_emails", duration, len(unseen_emails))
        
        self.disconnect()
        return unseen_emails


def get_mail_provider() -> MailProvider:
    """Factory function to get the appropriate mail provider based on configuration"""
    provider_type = config.get("mail.provider", "gmail").lower()
    
    logger.info(f"Initializing mail provider: {provider_type}")
    
    if provider_type == "gmail":
        return GmailProvider()
    elif provider_type == "mock":
        return MockMailProvider()
    else:
        logger.error(f"Unknown mail provider type: {provider_type}")
        logger.info("Falling back to Gmail provider")
        return GmailProvider()


# Initialize the mail provider
try:
    mail_provider = get_mail_provider()
    logger.info(f"Mail provider initialized successfully: {type(mail_provider).__name__}")
except Exception as e:
    logger.critical(f"Failed to initialize mail provider: {e}")
    raise


# Public API functions (maintain backward compatibility)
def fetch_all_unseen_emails() -> List[Tuple[str, str, str, int, str]]:
    """
    Fetch all unseen emails using the configured mail provider.
    
    Returns:
        List of tuples containing (sender, subject, body, uid, thread_id)
    """
    return mail_provider.fetch_unseen_emails()


def fetch_all_unseen_emails_and_mark_processed() -> List[Tuple[str, str, str, int, str]]:
    """
    Fetch all unseen emails and mark them as processed using the configured mail provider.
    
    Returns:
        List of tuples containing (sender, subject, body, uid, thread_id)
    """
    return mail_provider.fetch_unseen_emails_and_mark_processed()


def mark_email_as_processed(uid: int) -> bool:
    """
    Mark a specific email as processed using the configured mail provider.
    
    Args:
        uid: Email unique identifier
        
    Returns:
        bool: True if marking successful, False otherwise
    """
    return mail_provider.mark_email_as_processed(uid)


def fetch_latest_email() -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Legacy function for backward compatibility.
    Returns the newest unseen email in the old format.
    """
    logger.info("Legacy function called: fetch_latest_email")
    logger.warning("Consider using fetch_all_unseen_emails() for better performance")
    
    emails = fetch_all_unseen_emails()
    if not emails:
        logger.info("No emails found for legacy fetch_latest_email")
        return None, None, None
    
    # Return the last email (newest) in the old format
    sender, subject, body, uid, thread_id = emails[-1]
    logger.info(f"Returning latest email UID {uid} for legacy compatibility")
    return sender, subject, body


# Legacy functions for backward compatibility
def clean_subject(raw_subject: str) -> str:
    """Legacy function - now handled by provider"""
    logger.warning("clean_subject() called directly - consider using provider methods")
    if hasattr(mail_provider, '_clean_subject'):
        return mail_provider._clean_subject(raw_subject)
    else:
        # Fallback for non-Gmail providers
        return raw_subject


def create_ai_label(server=None, label_name: str = None) -> bool:
    """Legacy function - now handled by provider"""
    logger.warning("create_ai_label() called directly - functionality moved to provider")
    return True  # Return True for compatibility


if __name__ == "__main__":
    from logger_config import setup_logging
    
    # Enable debug logging for testing
    setup_logging(log_level="DEBUG")
    
    current_provider = type(mail_provider).__name__
    logger.info(f"Testing mail reader with provider: {current_provider}")
    
    logger.info("First run - should find emails:")
    emails = fetch_all_unseen_emails_and_mark_processed()
    logger.info(f"Found {len(emails)} emails")
    
    for i, (sender, subject, body, uid, thread_id) in enumerate(emails):
        logger.info(f"\n{i+1}. Email UID: {uid}")
        logger.info(f"   From: {sender}")
        logger.info(f"   Subject: {subject}")
        logger.info(f"   Thread ID: {thread_id}")
        logger.info(f"   Body preview: {body[:100]}..." if len(body) > 100 else f"   Body: {body}")
    
    logger.info("\n" + "="*50)
    logger.info("Second run - testing processed email tracking:")
    
    emails_second = fetch_all_unseen_emails_and_mark_processed()
    logger.info(f"Found {len(emails_second)} emails")
    
    if current_provider == "MockMailProvider":
        if len(emails_second) == 0:
            logger.info(" Success! Mock provider correctly tracks processed emails")
        else:
            logger.warning(" Issue: Mock provider should not return already processed emails")
    else:
        if len(emails_second) == 0:
            logger.info(" Success! Gmail labeling working - no duplicate processing")
        else:
            logger.warning(" Issue: Still finding emails that should be labeled")
    
    # Test switching providers
    logger.info(f"\nTesting with {current_provider} provider complete!")
    logger.info("To test provider switching, change 'mail.provider' in config.yaml to 'mock' or 'gmail'")