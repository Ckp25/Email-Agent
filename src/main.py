import sys
import os
import time
from datetime import datetime
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from mail_reader import fetch_all_unseen_emails_and_mark_processed
from mail_sender import send_replies_for_emails
# Updated import to use enhanced reply generation
from get_reply import generate_enhanced_reply
from thread_manager import add_email_to_thread, get_thread_stats
from logger_config import get_logger, setup_logging, log_email_operation, log_performance
from config_loader import config

# Initialize logger for main process
logger = get_logger("main")

def main():
    """Main email processing pipeline with enhanced classification and document integration."""
    start_time = time.time()
    
    logger.info("="*60)
    logger.info("ENHANCED EMAIL BOT PROCESSING STARTED")
    logger.info("="*60)
    logger.info(f"Process started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Log environment information
    logger.debug(f"Python version: {sys.version}")
    logger.debug(f"Working directory: {os.getcwd()}")
    
    # Log current thread statistics before processing
    logger.info("Current thread storage status:")
    initial_stats = get_thread_stats()
    for key, value in initial_stats.items():
        logger.info(f"  {key}: {value}")
    
    try:
        # Step 1: Fetch emails
        logger.info("\n--- STEP 1: FETCHING EMAILS ---")
        fetch_start_time = time.time()
        
        emails = fetch_all_unseen_emails_and_mark_processed()
        
        fetch_duration = time.time() - fetch_start_time
        log_performance(logger, "email fetching", fetch_duration, len(emails))

        if not emails:
            logger.info("No new emails found to process")
            logger.info("Email bot process completed - nothing to do")
            total_duration = time.time() - start_time
            logger.info(f"Total runtime: {total_duration:.2f} seconds")
            return

        log_email_operation(logger, "fetched", len(emails), "for processing")

        # Log email summary
        logger.info(f"Processing {len(emails)} emails:")
        for i, (sender, subject, body, uid, thread_id) in enumerate(emails, 1):
            logger.info(f"{i:2d}. UID {uid:4d} | {sender[:30]:30s} | {subject[:40]:40s}")
            logger.debug(f"    Thread: {thread_id} | Body length: {len(body)} chars")
        
        # Step 2: Generate enhanced replies with classification and document selection
        logger.info("\n--- STEP 2: GENERATING ENHANCED REPLIES WITH CLASSIFICATION ---")
        reply_start_time = time.time()
        
        enhanced_results = []
        successful_replies = 0
        failed_replies = 0
        high_priority_emails = 0
        total_documents_selected = 0
        classification_summary = {}
        
        for i, (sender, subject, body, uid, thread_id) in enumerate(emails, 1):
            try:
                logger.info(f"\nProcessing email {i}/{len(emails)} - UID: {uid}")
                logger.info(f"From: {sender}")
                logger.info(f"Subject: {subject}")
                
                # Generate enhanced reply with classification and document selection
                reply, document_paths, classification_info = generate_enhanced_reply(
                    subject, body, sender, thread_id
                )
                
                if reply.strip():
                    successful_replies += 1
                    logger.info(f"Successfully generated enhanced reply for UID {uid}")
                    
                    # Log classification results
                    category = classification_info.get('category', 'unknown')
                    interest_level = classification_info.get('interest_level', 'unknown')
                    confidence = classification_info.get('confidence', 0)
                    needs_review = classification_info.get('needs_human_review', False)
                    
                    logger.info(f"Classification: {category} (confidence: {confidence:.2f})")
                    logger.info(f"Interest Level: {interest_level}")
                    logger.info(f"Human Review Needed: {needs_review}")
                    
                    if needs_review:
                        high_priority_emails += 1
                        logger.warning(f"UID {uid} flagged for human review!")
                    
                    # Log document selection
                    if document_paths:
                        total_documents_selected += len(document_paths)
                        logger.info(f"Selected {len(document_paths)} documents:")
                        for doc_path in document_paths:
                            doc_name = os.path.basename(doc_path)
                            logger.info(f"  - {doc_name}")
                    else:
                        logger.info("No documents selected for this email")
                    
                    # Track classification categories
                    if category in classification_summary:
                        classification_summary[category] += 1
                    else:
                        classification_summary[category] = 1
                    
                else:
                    failed_replies += 1
                    logger.warning(f"Failed to generate reply for UID {uid}")
                    classification_info = {"error": "Reply generation failed"}
                    document_paths = []
                
                # Store results for sending phase
                enhanced_results.append({
                    'email_data': (sender, subject, body, uid, thread_id),
                    'reply': reply,
                    'documents': document_paths,
                    'classification': classification_info
                })
                
            except Exception as e:
                logger.error(f"Error processing email UID {uid}: {e}")
                failed_replies += 1
                enhanced_results.append({
                    'email_data': (sender, subject, body, uid, thread_id),
                    'reply': "",
                    'documents': [],
                    'classification': {"error": str(e)}
                })
        
        reply_duration = time.time() - reply_start_time
        log_performance(logger, "enhanced reply generation", reply_duration, len(emails))
        
        # Log enhanced reply generation summary
        logger.info(f"\nEnhanced reply generation results:")
        logger.info(f"  Successful: {successful_replies}")
        logger.info(f"  Failed: {failed_replies}")
        logger.info(f"  High priority (needs review): {high_priority_emails}")
        logger.info(f"  Total documents selected: {total_documents_selected}")
        
        logger.info(f"\nClassification breakdown:")
        for category, count in classification_summary.items():
            logger.info(f"  {category}: {count} emails")
        
        if failed_replies > 0:
            failed_uids = [result['email_data'][3] for result in enhanced_results if not result['reply'].strip()]
            logger.warning(f"Failed to generate replies for UIDs: {failed_uids}")
        
        # Step 3: Prepare data for sending (convert to old format for compatibility)
        logger.info("\n--- STEP 3: PREPARING FOR SENDING ---")
        
        # Convert enhanced results back to format expected by mail sender
        replies_for_sender = []
        emails_for_sender = []
        document_attachment_map = {}  # UID -> list of document paths
        
        for result in enhanced_results:
            email_data = result['email_data']
            reply = result['reply']
            documents = result['documents']
            
            uid = email_data[3]
            emails_for_sender.append(email_data)
            replies_for_sender.append((uid, reply))
            
            if documents:
                document_attachment_map[uid] = documents
        
        logger.info(f"Prepared {len(replies_for_sender)} replies for sending")
        logger.info(f"Emails with attachments: {len(document_attachment_map)}")
        
        # Step 4: Send replies with document attachments
        logger.info("\n--- STEP 4: SENDING REPLIES WITH ATTACHMENTS ---")
        send_start_time = time.time()
        
        logger.info(f"Sending {len(replies_for_sender)} replies")
        if document_attachment_map:
            logger.info(f"Including attachments for {len(document_attachment_map)} emails")
            for uid, docs in document_attachment_map.items():
                doc_names = [os.path.basename(doc) for doc in docs]
                logger.info(f"  UID {uid}: {', '.join(doc_names)}")
        else:
            logger.info("No document attachments to include")
        
        results = send_replies_for_emails(emails_for_sender, replies_for_sender, document_attachment_map)
        
        send_duration = time.time() - send_start_time
        log_performance(logger, "email sending", send_duration, len(emails))
        
        # Analyze sending results
        successful_sends = sum(1 for _, success in results if success)
        failed_sends = len(results) - successful_sends
        
        logger.info(f"Email sending results:")
        logger.info(f"  Successful: {successful_sends}")
        logger.info(f"  Failed: {failed_sends}")
        
        if failed_sends > 0:
            failed_send_uids = [uid for uid, success in results if not success]
            logger.warning(f"Failed to send emails for UIDs: {failed_send_uids}")
        
        # Step 5: Save to thread storage
        logger.info("\n--- STEP 5: SAVING TO THREAD STORAGE ---")
        storage_start_time = time.time()
        
        result_dict = {uid: success for uid, success in results}
        storage_successes = 0
        storage_failures = 0
        
        for result in enhanced_results:
            sender, subject, body, uid, thread_id = result['email_data']
            reply = result['reply']
            
            try:
                # Save the original email to thread
                logger.debug(f"Saving original email UID {uid} to thread {thread_id}")
                original_saved = add_email_to_thread(thread_id, sender, subject, body, uid, is_bot_reply=False)
                
                if not original_saved:
                    logger.warning(f"Failed to save original email UID {uid} to thread storage")
                    storage_failures += 1
                    continue
                
                # Save the bot reply to thread (if reply was generated and sent successfully)
                if reply and reply.strip() and result_dict.get(uid, False):
                    bot_email = config.email_address
                    reply_subject = "Re: " + subject.strip()
                    
                    logger.debug(f"Saving bot reply for UID {uid} to thread {thread_id}")
                    reply_saved = add_email_to_thread(thread_id, bot_email, reply_subject, reply, None, is_bot_reply=True)
                    
                    if reply_saved:
                        logger.debug(f"Successfully saved conversation pair for thread {thread_id}")
                        storage_successes += 1
                    else:
                        logger.warning(f"Failed to save bot reply for UID {uid} to thread storage")
                        storage_failures += 1
                else:
                    if not reply or not reply.strip():
                        logger.debug(f"No reply generated for UID {uid}, only saving original email")
                    elif not result_dict.get(uid, False):
                        logger.debug(f"Reply not sent for UID {uid}, only saving original email")
                    
                    storage_successes += 1
                    
            except Exception as e:
                logger.error(f"Error saving UID {uid} to thread storage: {e}")
                storage_failures += 1
        
        storage_duration = time.time() - storage_start_time
        log_performance(logger, "thread storage", storage_duration, len(emails))
        
        logger.info(f"Thread storage results:")
        logger.info(f"  Successful: {storage_successes}")
        logger.info(f"  Failed: {storage_failures}")
        
        # Step 6: Final summary with enhanced statistics
        logger.info("\n--- ENHANCED PROCESSING SUMMARY ---")
        
        total_duration = time.time() - start_time
        
        # Overall process statistics
        logger.info(f"Process Summary:")
        logger.info(f"  Emails processed: {len(emails)}")
        logger.info(f"  Replies generated: {successful_replies}/{len(emails)}")
        logger.info(f"  Emails sent: {successful_sends}/{len(emails)}")
        logger.info(f"  Thread storage: {storage_successes}/{len(emails)}")
        logger.info(f"  Total runtime: {total_duration:.2f} seconds")
        
        # Enhanced statistics
        logger.info(f"Enhanced Features:")
        logger.info(f"  High priority emails: {high_priority_emails}")
        logger.info(f"  Documents selected: {total_documents_selected}")
        logger.info(f"  Emails with attachments: {len(document_attachment_map)}")
        
        # Classification breakdown
        logger.info(f"Classification Results:")
        for category, count in classification_summary.items():
            percentage = (count / len(emails)) * 100
            logger.info(f"  {category}: {count} ({percentage:.1f}%)")
        
        # Calculate success rates
        if len(emails) > 0:
            reply_rate = (successful_replies / len(emails)) * 100
            send_rate = (successful_sends / len(emails)) * 100
            storage_rate = (storage_successes / len(emails)) * 100
            
            logger.info(f"Success Rates:")
            logger.info(f"  Reply generation: {reply_rate:.1f}%")
            logger.info(f"  Email sending: {send_rate:.1f}%")
            logger.info(f"  Thread storage: {storage_rate:.1f}%")
            
            # Overall success (email sent successfully)
            overall_success_rate = send_rate
            if overall_success_rate == 100:
                logger.info("Perfect success rate achieved!")
            elif overall_success_rate >= 80:
                logger.info("Good success rate achieved")
            else:
                logger.warning(f"Low overall success rate: {overall_success_rate:.1f}%")
        
        # Processing rate
        if total_duration > 0:
            processing_rate = len(emails) / total_duration
            logger.info(f"Processing rate: {processing_rate:.1f} emails/second")
        
        # Log updated thread statistics
        logger.info("\nUpdated thread storage status:")
        final_stats = get_thread_stats()
        for key, value in final_stats.items():
            # Only calculate change for numeric values
            if isinstance(value, (int, float)) and isinstance(initial_stats.get(key, 0), (int, float)):
                change = value - initial_stats.get(key, 0)
                change_str = f" (+{change})" if change > 0 else f" ({change})" if change < 0 else ""
                logger.info(f"  {key}: {value}{change_str}")
            else:
                logger.info(f"  {key}: {value}")
        
        # Final status
        if failed_replies > 0 or failed_sends > 0 or storage_failures > 0:
            logger.warning("Process completed with some failures - check logs above for details")
        elif high_priority_emails > 0:
            logger.warning(f"Process completed successfully, but {high_priority_emails} emails need human review")
        else:
            logger.info("Process completed successfully with no issues!")
        
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(f"Critical error in main process after {total_duration:.2f}s: {e}")
        logger.error("Enhanced email bot process failed - check logs for details")
        raise
    
    finally:
        total_duration = time.time() - start_time
        logger.info("="*60)
        logger.info("ENHANCED EMAIL BOT PROCESSING COMPLETED")
        logger.info(f"Total execution time: {total_duration:.2f} seconds")
        logger.info(f"Process ended at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)

if __name__ == "__main__":
    # Configure logging using centralized config
    setup_logging(
        log_level=config.log_level,
        log_to_file=config.log_to_file,
        log_file_path=config.log_file_path,
        console_colors=config.get("logging.console_colors", True),
        max_file_size_mb=config.get("logging.max_file_size_mb", 10),
        backup_count=config.get("logging.backup_count", 5)
    )
    
    try:
        main()
    except KeyboardInterrupt:
        logger.warning("Process interrupted by user (Ctrl+C)")
    except Exception as e:
        logger.critical(f"Unhandled exception in main: {e}")
        sys.exit(1)