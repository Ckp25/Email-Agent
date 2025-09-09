import yagmail
import os
import time
import re
from typing import List, Optional
from logger_config import get_logger, log_batch_start, log_batch_complete, log_performance
from config_loader import config

# Initialize logger for this module
logger = get_logger("mail_sender")

# Load configuration values
EMAIL = config.email_address
PASSWORD = config.email_password
SMTP_TIMEOUT = config.get("smtp.timeout_seconds", 30)
RETRY_ATTEMPTS = config.get("smtp.retry_attempts", 3)
RETRY_DELAY = config.get("smtp.retry_delay_seconds", 5)

# Attachment configuration
MAX_ATTACHMENT_SIZE_MB = config.get("smtp.max_attachment_size_mb", 25)  # Gmail limit is 25MB
ALLOWED_ATTACHMENT_TYPES = config.get("smtp.allowed_attachment_types", [".pdf", ".doc", ".docx", ".txt"])

logger.info(f"Enhanced mail sender initialized for account: {EMAIL}")
logger.debug(f"SMTP timeout: {SMTP_TIMEOUT}s, Max retries: {RETRY_ATTEMPTS}")
logger.debug(f"Max attachment size: {MAX_ATTACHMENT_SIZE_MB}MB")
logger.debug(f"Allowed attachment types: {ALLOWED_ATTACHMENT_TYPES}")

def extract_email_address(from_field: str) -> str:
    """Extract email address from From field which might be in format 'Name <email@domain.com>'"""
    if not from_field:
        logger.warning("Empty from_field provided to extract_email_address")
        return ""
    
    logger.debug(f"Extracting email from: {from_field}")
    
    try:
        # Look for email in angle brackets first
        match = re.search(r'<(.+?)>', from_field)
        if match:
            extracted = match.group(1)
            logger.debug(f"Extracted email from angle brackets: {extracted}")
            return extracted
        
        # If no angle brackets, assume the whole string is the email
        cleaned = from_field.strip()
        logger.debug(f"No angle brackets found, using as-is: {cleaned}")
        return cleaned
        
    except Exception as e:
        logger.error(f"Error extracting email address from '{from_field}': {e}")
        return from_field.strip()  # Return original if extraction fails

def validate_attachment_file(file_path: str) -> tuple[bool, str]:
    """
    Validate attachment file exists, has allowed type, and size is within limits.
    
    Args:
        file_path: Path to the attachment file
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    if not file_path:
        return False, "Empty file path provided"
    
    logger.debug(f"Validating attachment: {file_path}")
    
    # Check if file exists
    if not os.path.exists(file_path):
        error_msg = f"Attachment file not found: {file_path}"
        logger.error(error_msg)
        return False, error_msg
    
    # Check if it's a file (not directory)
    if not os.path.isfile(file_path):
        error_msg = f"Attachment path is not a file: {file_path}"
        logger.error(error_msg)
        return False, error_msg
    
    # Check file extension
    file_ext = os.path.splitext(file_path)[1].lower()
    if file_ext not in ALLOWED_ATTACHMENT_TYPES:
        error_msg = f"Attachment type not allowed: {file_ext}. Allowed: {ALLOWED_ATTACHMENT_TYPES}"
        logger.warning(error_msg)
        return False, error_msg
    
    # Check file size
    try:
        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = file_size_bytes / (1024 * 1024)
        
        if file_size_mb > MAX_ATTACHMENT_SIZE_MB:
            error_msg = f"Attachment too large: {file_size_mb:.1f}MB (max: {MAX_ATTACHMENT_SIZE_MB}MB)"
            logger.error(error_msg)
            return False, error_msg
        
        logger.debug(f"Attachment validation passed: {os.path.basename(file_path)} ({file_size_mb:.1f}MB)")
        return True, ""
        
    except Exception as e:
        error_msg = f"Error checking file size for {file_path}: {e}"
        logger.error(error_msg)
        return False, error_msg

def send_reply(to_address: str, subject: str, body: str, attachments: Optional[List[str]] = None) -> bool:
    """
    Sends an email from your bot to the given address with subject, body, and optional attachments.
    
    Args:
        to_address: The recipient's email address
        subject: The original email subject
        body: The reply message body
        attachments: Optional list of file paths to attach
        
    Returns:
        bool: True if email was sent successfully, False otherwise
    """
    start_time = time.time()
    
    logger.info(f"Attempting to send reply to: {to_address}")
    logger.debug(f"Subject: {subject}")
    logger.debug(f"Body length: {len(body)} characters")
    
    # Handle attachments
    attachment_count = 0
    valid_attachments = []
    attachment_errors = []
    
    if attachments:
        logger.info(f"Processing {len(attachments)} potential attachments")
        
        for attachment_path in attachments:
            is_valid, error_msg = validate_attachment_file(attachment_path)
            
            if is_valid:
                valid_attachments.append(attachment_path)
                attachment_count += 1
                attachment_name = os.path.basename(attachment_path)
                logger.info(f"Valid attachment: {attachment_name}")
            else:
                attachment_errors.append(f"{os.path.basename(attachment_path)}: {error_msg}")
                logger.warning(f"Invalid attachment: {error_msg}")
        
        if attachment_errors:
            logger.warning(f"Skipping {len(attachment_errors)} invalid attachments")
            for error in attachment_errors:
                logger.warning(f"  - {error}")
    
    logger.info(f"Sending email with {attachment_count} valid attachments")
    
    # Validate inputs
    if not all([to_address, subject, body]):
        missing_fields = []
        if not to_address: missing_fields.append("to_address")
        if not subject: missing_fields.append("subject")
        if not body: missing_fields.append("body")
        
        logger.error(f"Missing required email parameters: {', '.join(missing_fields)}")
        return False
    
    # Validate email address format (basic check)
    if "@" not in to_address or "." not in to_address:
        logger.error(f"Invalid email address format: {to_address}")
        return False
    
    try:
        logger.debug("Initializing yagmail SMTP connection")
        smtp_start_time = time.time()
        
        with yagmail.SMTP(EMAIL, PASSWORD) as yag:
            smtp_connection_time = time.time() - smtp_start_time
            logger.debug(f"SMTP connection established in {smtp_connection_time:.2f}s")
            
            reply_subject = "Re: " + subject.strip()
            logger.debug(f"Final subject line: {reply_subject}")
            
            # Prepare email contents
            email_contents = [body]  # Start with text body
            
            # Add attachments if any
            if valid_attachments:
                logger.debug(f"Adding {len(valid_attachments)} attachments to email")
                for attachment_path in valid_attachments:
                    email_contents.append(attachment_path)
                    attachment_name = os.path.basename(attachment_path)
                    file_size_mb = os.path.getsize(attachment_path) / (1024 * 1024)
                    logger.debug(f"  Added: {attachment_name} ({file_size_mb:.1f}MB)")
            
            # Send the email
            send_start_time = time.time()
            yag.send(to=to_address, subject=reply_subject, contents=email_contents)
            send_duration = time.time() - send_start_time
            
            total_duration = time.time() - start_time
            
            logger.info(f"Successfully sent reply to: {to_address}")
            logger.info(f"Email included {attachment_count} attachments")
            logger.debug(f"Email sending took {send_duration:.2f}s (total: {total_duration:.2f}s)")
            log_performance(logger, "email send with attachments", total_duration, 1)
            
            return True
            
    except Exception as e:
        total_duration = time.time() - start_time
        
        # Categorize different types of SMTP errors
        error_str = str(e).lower()
        if "authentication" in error_str or "username" in error_str or "password" in error_str:
            logger.error(f"SMTP authentication failed for {to_address}: {e}")
        elif "connection" in error_str or "timeout" in error_str:
            logger.error(f"SMTP connection failed for {to_address}: {e}")
        elif "recipient" in error_str or "mailbox" in error_str:
            logger.error(f"Invalid recipient address {to_address}: {e}")
        elif "quota" in error_str or "limit" in error_str:
            logger.error(f"Sending quota/limit reached for {to_address}: {e}")
        elif "attachment" in error_str or "size" in error_str:
            logger.error(f"Attachment-related error for {to_address}: {e}")
        else:
            logger.error(f"Unknown SMTP error sending to {to_address}: {e}")
        
        logger.debug(f"Failed email send took {total_duration:.2f}s")
        return False

def send_replies_for_emails(emails: list[tuple[str, str, str, int, str]], replies: list[tuple[int, str]], 
                          document_attachments: Optional[dict[int, List[str]]] = None) -> list[tuple[int, bool]]:
    """
    Send replies for a batch of emails with optional document attachments.
    
    Args:
        emails: List of (sender, subject, body, uid, thread_id) tuples
        replies: List of (uid, reply_text) tuples from generate_replies_for_emails
        document_attachments: Optional dict mapping UID to list of document file paths
        
    Returns:
        List of (uid, success) tuples indicating which emails were sent successfully
    """
    start_time = time.time()
    email_count = len(emails)
    
    logger.info(f"Starting enhanced batch email sending for {email_count} emails")
    log_batch_start(logger, "enhanced email sending", email_count)
    
    if not emails:
        logger.warning("No emails provided for batch sending")
        return []
    
    if not replies:
        logger.warning("No replies provided for batch sending")
        return []
    
    # Initialize attachment tracking
    document_attachments = document_attachments or {}
    total_attachments = sum(len(docs) for docs in document_attachments.values())
    emails_with_attachments = len(document_attachments)
    
    logger.info(f"Processing {len(emails)} emails with {len(replies)} replies")
    logger.info(f"Emails with attachments: {emails_with_attachments}")
    logger.info(f"Total attachments to send: {total_attachments}")
    
    results = []
    reply_dict = {uid: reply for uid, reply in replies}
    
    successful_sends = 0
    failed_sends = 0
    skipped_sends = 0
    total_reply_length = 0
    successful_attachments = 0
    failed_attachments = 0
    
    for i, (sender, subject, body, uid, thread_id) in enumerate(emails, 1):
        try:
            logger.info(f"\n--- Sending reply {i}/{email_count} ---")
            logger.info(f"UID: {uid}")
            logger.info(f"Original sender: {sender}")
            logger.info(f"Subject: {subject}")
            logger.debug(f"Thread ID: {thread_id}")
            
            # Check if we have a reply for this email
            if uid not in reply_dict:
                logger.warning(f"No reply found for UID {uid}, skipping")
                results.append((uid, False))
                skipped_sends += 1
                continue
            
            reply_text = reply_dict[uid]
            if not reply_text.strip():
                logger.warning(f"Empty reply for UID {uid}, skipping")
                results.append((uid, False))
                skipped_sends += 1
                continue
            
            # Extract recipient email address
            to_address = extract_email_address(sender)
            if not to_address:
                logger.error(f"Could not extract email address from '{sender}', skipping UID {uid}")
                results.append((uid, False))
                failed_sends += 1
                continue
            
            # Get attachments for this email
            attachments = document_attachments.get(uid, [])
            
            logger.debug(f"Sending to extracted address: {to_address}")
            logger.debug(f"Reply length: {len(reply_text)} characters")
            logger.debug(f"Attachments: {len(attachments)} files")
            
            if attachments:
                logger.info(f"Including {len(attachments)} document attachments:")
                for attachment_path in attachments:
                    attachment_name = os.path.basename(attachment_path)
                    logger.info(f"  - {attachment_name}")
            
            # Send the reply with attachments
            send_start_time = time.time()
            success = send_reply(to_address, subject, reply_text, attachments)
            send_duration = time.time() - send_start_time
            
            results.append((uid, success))
            
            if success:
                successful_sends += 1
                total_reply_length += len(reply_text)
                
                # Count successful attachments
                if attachments:
                    # Validate attachments that were actually sent
                    valid_attachment_count = 0
                    for attachment_path in attachments:
                        is_valid, _ = validate_attachment_file(attachment_path)
                        if is_valid:
                            valid_attachment_count += 1
                    
                    successful_attachments += valid_attachment_count
                    if valid_attachment_count < len(attachments):
                        failed_attachments += (len(attachments) - valid_attachment_count)
                
                logger.info(f"Successfully sent reply for UID {uid} in {send_duration:.2f}s")
            else:
                failed_sends += 1
                if attachments:
                    failed_attachments += len(attachments)
                logger.warning(f"Failed to send reply for UID {uid}")
            
        except Exception as e:
            logger.error(f"Unexpected error processing UID {uid}: {e}")
            results.append((uid, False))
            failed_sends += 1
            
            # Count failed attachments
            if uid in document_attachments:
                failed_attachments += len(document_attachments[uid])
    
    # Final batch statistics
    total_duration = time.time() - start_time
    
    log_batch_complete(logger, "enhanced email sending", successful_sends, failed_sends + skipped_sends)
    log_performance(logger, "batch email sending with attachments", total_duration, email_count)
    
    # Enhanced attachment statistics
    logger.info(f"Attachment Results:")
    logger.info(f"  Successfully sent: {successful_attachments}")
    logger.info(f"  Failed to send: {failed_attachments}")
    logger.info(f"  Total attempted: {successful_attachments + failed_attachments}")
    
    if successful_attachments + failed_attachments > 0:
        attachment_success_rate = (successful_attachments / (successful_attachments + failed_attachments)) * 100
        logger.info(f"  Attachment success rate: {attachment_success_rate:.1f}%")
    
    # Additional statistics
    if successful_sends > 0:
        avg_reply_length = total_reply_length / successful_sends
        logger.info(f"Average sent reply length: {avg_reply_length:.0f} characters")
    
    if skipped_sends > 0:
        logger.info(f"Skipped {skipped_sends} emails (no reply or empty reply)")
    
    # Success rate analysis
    total_attempted = email_count - skipped_sends
    if total_attempted > 0:
        success_rate = (successful_sends / total_attempted) * 100
        logger.info(f"Send success rate: {success_rate:.1f}% ({successful_sends}/{total_attempted})")
        
        if success_rate < 80:
            logger.warning(f"Low success rate detected: {success_rate:.1f}%")
        elif success_rate == 100:
            logger.info("Perfect send success rate achieved!")
    
    if total_duration > 0:
        rate = successful_sends / (total_duration / 60)  # emails per minute
        logger.info(f"Sending rate: {rate:.1f} emails/minute")
    
    logger.info(f"Enhanced batch email sending complete:")
    logger.info(f"  Emails: {successful_sends} sent, {failed_sends} failed, {skipped_sends} skipped")
    logger.info(f"  Attachments: {successful_attachments} sent, {failed_attachments} failed")
    
    return results

# Legacy function for backward compatibility (without attachments)
def send_reply_legacy(to_address: str, subject: str, body: str) -> bool:
    """Legacy send_reply function without attachments for backward compatibility"""
    logger.warning("Using legacy send_reply function - consider updating to use attachments")
    return send_reply(to_address, subject, body, None)

if __name__ == "__main__":
    from logger_config import setup_logging
    from mail_reader import fetch_all_unseen_emails_and_mark_processed
    from get_reply import generate_enhanced_reply
    
    # Enable debug logging for testing
    setup_logging(log_level="DEBUG")
    
    logger.info("Testing enhanced email sending with document attachments...")
    
    # Test attachment validation
    logger.info("\n--- Testing Attachment Validation ---")
    
    test_files = [
        "documents/geotextile_catalog.pdf",
        "documents/coastal_protection_guide.pdf", 
        "documents/nonexistent.pdf",
        "config.yaml"  # Wrong type
    ]
    
    for test_file in test_files:
        is_valid, error_msg = validate_attachment_file(test_file)
        status = "VALID" if is_valid else "INVALID"
        logger.info(f"{status}: {test_file}")
        if not is_valid:
            logger.info(f"  Error: {error_msg}")
    
    # Test with real emails if available
    logger.info("\n--- Testing with Real Emails ---")
    emails = fetch_all_unseen_emails_and_mark_processed()
    
    if emails:
        # Take first email for testing
        sender, subject, body, uid, thread_id = emails[0]
        
        logger.info(f"Testing with email UID {uid} from {sender}")
        
        # Generate enhanced reply to get document recommendations
        reply, documents, classification = generate_enhanced_reply(subject, body, sender, thread_id)
        
        logger.info(f"Generated reply with {len(documents)} recommended documents")
        
        # Test sending with attachments
        to_address = extract_email_address(sender)
        logger.info(f"Would send to: {to_address}")
        logger.info(f"With attachments: {[os.path.basename(doc) for doc in documents]}")
        
        # Don't actually send in test mode
        logger.info("Test mode - not actually sending email")
        
    else:
        logger.info("No emails available for testing")
    
    logger.info("Enhanced mail sender testing complete!")