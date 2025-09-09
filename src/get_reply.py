import os
import time
from abc import ABC, abstractmethod
from openai import OpenAI
from thread_manager import get_thread_history, format_thread_context
from logger_config import get_logger, log_api_call, log_batch_start, log_batch_complete, log_performance
from config_loader import config

# Import our new modules
from email_classifier import classify_email, should_flag_for_human_review, get_recommended_documents
from document_manager import search_documents_by_category, get_documents_for_llm_selection

# Initialize logger for this module
logger = get_logger("get_reply")


class AIProvider(ABC):
    """Abstract base class for AI providers"""
    
    @abstractmethod
    def generate_reply(self, email_body: str, thread_id: str = None, classification_context: dict = None) -> tuple[str, list]:
        """
        Generate a reply to an email.
        
        Args:
            email_body: The email content to reply to
            thread_id: Optional thread ID for conversation context
            classification_context: Dict with classification and document info
            
        Returns:
            Tuple of (reply_text, recommended_document_paths)
        """
        pass


class OpenAIProvider(AIProvider):
    """OpenAI GPT provider implementation with classification integration"""
    
    def __init__(self):
        try:
            self.api_key = config.openai_api_key
            self.model = config.openai_model
            self.temperature = config.openai_temperature
            self.max_retries = config.openai_max_retries
            
            logger.info("Enhanced OpenAI provider configuration loaded successfully")
            logger.debug(f"Model: {self.model}, Temperature: {self.temperature}, Max retries: {self.max_retries}")
            
            self.client = OpenAI(api_key=self.api_key)
            logger.info("OpenAI client initialized successfully")
            
        except Exception as e:
            logger.critical(f"Error initializing OpenAI provider: {e}")
            raise
    
    def generate_reply(self, email_body: str, thread_id: str = None, classification_context: dict = None) -> tuple[str, list]:
        """Generate a reply using OpenAI GPT-4o with classification context"""
        start_time = time.time()
        
        if thread_id:
            logger.info(f"Generating enhanced reply for thread {thread_id}")
        else:
            logger.info("Generating enhanced reply for new conversation")
        
        try:
            # Get thread context if available
            thread_context = ""
            if thread_id:
                thread_history = get_thread_history(thread_id)
                if thread_history:
                    thread_context = format_thread_context(thread_history) + "\n\n"
                    logger.info(f"Using thread context with {len(thread_history)} previous messages")
            
            # Get classification info
            classification = classification_context.get('classification') if classification_context else None
            recommended_docs = []
            
            if classification:
                logger.info(f"Using classification: {classification.primary_category} ({classification.interest_level})")
                
                # Get recommended document categories
                doc_categories = get_recommended_documents(classification)
                matching_docs = search_documents_by_category(doc_categories)
                
                if matching_docs:
                    recommended_docs = [doc['file_path'] for doc in matching_docs[:3]]  # Max 3 docs
                    doc_names = [doc['display_name'] for doc in matching_docs[:3]]
                    logger.info(f"Selected {len(recommended_docs)} documents: {', '.join(doc_names)}")
            
            # Build enhanced prompt with classification context
            prompt_parts = []
            
            # System context
            prompt_parts.append("You are a professional customer service representative for a geotextile manufacturing company.")
            prompt_parts.append("You provide helpful, accurate information about geotextile products and applications.")
            
            # Classification context
            if classification:
                prompt_parts.append(f"\nEMAIL ANALYSIS:")
                prompt_parts.append(f"- Application Category: {classification.primary_category}")
                prompt_parts.append(f"- Customer Interest Level: {classification.interest_level}")
                prompt_parts.append(f"- Confidence: {classification.confidence_score:.2f}")
                if classification.keywords_found:
                    prompt_parts.append(f"- Key Topics: {', '.join(classification.keywords_found[:5])}")
            
            # Document context
            if recommended_docs:
                doc_info = []
                for doc in matching_docs[:3]:
                    doc_info.append(f"- {doc['display_name']}: {doc['description'][:100]}...")
                
                prompt_parts.append(f"\nRELEVANT DOCUMENTS TO MENTION:")
                prompt_parts.extend(doc_info)
                prompt_parts.append("\nMention that you're attaching these documents in your response.")
            
            # Thread context
            if thread_context:
                prompt_parts.append(f"\nCONVERSATION HISTORY:")
                prompt_parts.append(thread_context)
            
            # Instructions
            prompt_parts.append(f"\nCUSTOMER EMAIL:")
            prompt_parts.append(email_body.strip())
            prompt_parts.append(f"\nINSTRUCTIONS:")
            
            if classification and classification.interest_level == "high_interest":
                prompt_parts.append("- This customer shows high buying interest - provide detailed, helpful information")
                prompt_parts.append("- Ask relevant follow-up questions about their project")
                prompt_parts.append("- Offer to schedule a call or provide a detailed quotation")
            elif classification and classification.interest_level == "medium_interest":
                prompt_parts.append("- This customer is in evaluation phase - provide good technical information")
                prompt_parts.append("- Guide them toward more specific requirements")
            else:
                prompt_parts.append("- Provide helpful general information")
                prompt_parts.append("- Encourage them to share more specific requirements")
            
            prompt_parts.append("- Keep response professional and concise")
            prompt_parts.append("- Include company expertise and capabilities")
            prompt_parts.append("- End with clear next steps")
            
            if recommended_docs:
                prompt_parts.append("- Mention the attached documents naturally in your response")
            
            base_prompt = "\n".join(prompt_parts)
            
            # Log prompt details
            prompt_length = len(base_prompt)
            logger.debug(f"Enhanced prompt length: {prompt_length} characters")
            
            # Make API call
            logger.debug("Making OpenAI API call with enhanced context")
            api_start_time = time.time()
            
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a professional geotextile company representative."},
                    {"role": "user", "content": base_prompt}
                ],
                temperature=self.temperature
            )
            
            api_duration = time.time() - api_start_time
            
            # Extract reply
            reply_content = response.choices[0].message.content or ""
            
            # Log results
            log_api_call(logger, f"Enhanced OpenAI {self.model}", True, f"response in {api_duration:.2f}s")
            
            reply_length = len(reply_content)
            logger.info(f"Generated enhanced reply: {reply_length} characters")
            
            if classification:
                logger.info(f"Reply context: {classification.primary_category} + {len(recommended_docs)} documents")
            
            # Token usage logging
            if hasattr(response, 'usage') and response.usage:
                usage = response.usage
                logger.info(f"Token usage - Prompt: {usage.prompt_tokens}, "
                           f"Completion: {usage.completion_tokens}, "
                           f"Total: {usage.total_tokens}")
            
            total_duration = time.time() - start_time
            log_performance(logger, "enhanced reply generation", total_duration, 1)
            
            return reply_content, recommended_docs

        except Exception as e:
            api_duration = time.time() - start_time
            log_api_call(logger, f"Enhanced OpenAI {self.model}", False, f"failed after {api_duration:.2f}s: {e}")
            
            logger.error(f"Enhanced OpenAI API error: {e}")
            logger.warning("Returning empty reply due to API failure")
            return "", []


class MockAIProvider(AIProvider):
    """Mock AI provider for testing with classification support"""
    
    def __init__(self):
        logger.info("Enhanced Mock AI provider initialized")
        self.call_count = 0
    
    def generate_reply(self, email_body: str, thread_id: str = None, classification_context: dict = None) -> tuple[str, list]:
        """Generate a mock reply with classification context"""
        start_time = time.time()
        self.call_count += 1
        
        logger.info(f"Generating enhanced mock reply #{self.call_count}")
        
        # Simulate processing time
        time.sleep(0.5)
        
        # Build mock response based on classification
        classification = classification_context.get('classification') if classification_context else None
        
        if classification:
            category = classification.primary_category
            interest = classification.interest_level
            
            if category == "coastal_erosion":
                reply = f"Thank you for your coastal protection inquiry. We have specialized solutions for marine environments. Mock response for {interest} interest customer."
                docs = ["documents/coastal_protection_guide.pdf"]
            elif category == "road_construction":
                reply = f"Thank you for your road construction inquiry. Our separation fabrics are ideal for your application. Mock response for {interest} interest customer."
                docs = ["documents/road_construction_solutions.pdf"]
            else:
                reply = f"Thank you for your inquiry about geotextiles. Please find our catalog attached. Mock response for {interest} interest customer."
                docs = ["documents/geotextile_catalog.pdf"]
        else:
            reply = "Thank you for your email. This is a mock response for testing purposes."
            docs = []
        
        if thread_id:
            reply += f" (Thread: {thread_id})"
        
        duration = time.time() - start_time
        logger.info(f"Generated enhanced mock reply in {duration:.2f}s with {len(docs)} documents")
        
        return reply, docs


def get_ai_provider() -> AIProvider:
    """Factory function to get the appropriate AI provider"""
    provider_type = config.get("ai.provider", "openai").lower()
    
    logger.info(f"Initializing enhanced AI provider: {provider_type}")
    
    if provider_type == "openai":
        return OpenAIProvider()
    elif provider_type == "mock":
        return MockAIProvider()
    else:
        logger.error(f"Unknown AI provider type: {provider_type}")
        logger.info("Falling back to OpenAI provider")
        return OpenAIProvider()


# Initialize the enhanced AI provider
try:
    ai_provider = get_ai_provider()
    logger.info(f"Enhanced AI provider initialized successfully: {type(ai_provider).__name__}")
except Exception as e:
    logger.critical(f"Failed to initialize enhanced AI provider: {e}")
    raise


def generate_reply(email_body: str, thread_id: str = None) -> str:
    """
    Backward compatibility function - generates reply without classification
    """
    reply, _ = ai_provider.generate_reply(email_body, thread_id)
    return reply


def generate_enhanced_reply(subject: str, email_body: str, sender: str = "", thread_id: str = None) -> tuple[str, list, dict]:
    """
    Generate enhanced reply with classification and document selection
    
    Returns:
        Tuple of (reply_text, document_paths, classification_info)
    """
    start_time = time.time()
    
    logger.info(f"Generating enhanced reply with classification for sender: {sender}")
    
    try:
        # Step 1: Classify the email
        logger.debug("Step 1: Classifying email")
        classification = classify_email(subject, email_body, sender)
        
        # Step 2: Check if needs human review
        needs_review = should_flag_for_human_review(classification)
        
        logger.info(f"Email classified as: {classification.primary_category} ({classification.interest_level})")
        if needs_review:
            logger.warning(f"Email flagged for human review: {classification.reasoning}")
        
        # Step 3: Generate reply with classification context
        logger.debug("Step 2: Generating AI reply with context")
        classification_context = {
            'classification': classification,
            'needs_human_review': needs_review
        }
        
        reply, recommended_docs = ai_provider.generate_reply(
            email_body, 
            thread_id, 
            classification_context
        )
        
        # Step 4: Prepare classification info for return
        classification_info = {
            'category': classification.primary_category,
            'interest_level': classification.interest_level,
            'confidence': classification.confidence_score,
            'needs_human_review': needs_review,
            'keywords': classification.keywords_found,
            'reasoning': classification.reasoning
        }
        
        total_duration = time.time() - start_time
        log_performance(logger, "complete enhanced reply generation", total_duration, 1)
        
        logger.info(f"Enhanced reply complete: {len(reply)} chars, {len(recommended_docs)} docs, review: {needs_review}")
        
        return reply, recommended_docs, classification_info
        
    except Exception as e:
        logger.error(f"Error in enhanced reply generation: {e}")
        logger.warning("Falling back to basic reply generation")
        
        # Fallback to basic reply
        basic_reply = generate_reply(email_body, thread_id)
        return basic_reply, [], {"error": str(e)}


def generate_replies_for_emails(emails: list[tuple[str, str, str, int, str]]) -> list[tuple[int, str]]:
    """
    Backward compatibility function for batch processing
    Uses basic reply generation without classification
    """
    start_time = time.time()
    email_count = len(emails)
    
    logger.info(f"Starting batch reply generation (basic mode) for {email_count} emails")
    log_batch_start(logger, "basic batch reply generation", email_count)
    
    replies = []
    successful_replies = 0
    failed_replies = 0
    
    for i, (sender, subject, body, uid, thread_id) in enumerate(emails, 1):
        try:
            logger.info(f"Processing email {i}/{email_count} - UID: {uid}")
            
            # Use basic reply generation for batch processing
            reply = generate_reply(body, thread_id)
            replies.append((uid, reply))
            
            if reply.strip():
                successful_replies += 1
                logger.info(f"Generated basic reply for UID {uid}")
            else:
                failed_replies += 1
                logger.warning(f"Failed to generate reply for UID {uid}")
                
        except Exception as e:
            logger.error(f"Error generating reply for UID {uid}: {e}")
            replies.append((uid, ""))
            failed_replies += 1
    
    total_duration = time.time() - start_time
    log_batch_complete(logger, "basic batch reply generation", successful_replies, failed_replies)
    log_performance(logger, "batch reply generation", total_duration, email_count)
    
    return replies


if __name__ == "__main__":
    from logger_config import setup_logging
    
    # Enable debug logging for testing
    setup_logging(log_level="DEBUG")
    
    logger.info("Testing enhanced reply generation with classification...")
    
    # Test enhanced reply generation
    test_emails = [
        {
            "sender": "engineer@coastal.com",
            "subject": "Coastal protection needed urgently",
            "body": "We have a coastal erosion project starting next month. Need 2000 sqm of marine-grade geotextiles for our seawall in Mumbai. Can you provide specs and pricing?",
            "thread_id": "test_coastal_123"
        },
        {
            "sender": "student@university.edu", 
            "subject": "General information request",
            "body": "Hi, I'm doing research on geotextiles. Can you send me some basic information about your products?",
            "thread_id": "test_general_456"
        }
    ]
    
    for i, email in enumerate(test_emails, 1):
        logger.info(f"\n{'='*60}")
        logger.info(f"TESTING ENHANCED REPLY {i}")
        logger.info(f"{'='*60}")
        
        logger.info(f"From: {email['sender']}")
        logger.info(f"Subject: {email['subject']}")
        logger.info(f"Body: {email['body'][:100]}...")
        
        # Generate enhanced reply
        reply, docs, classification = generate_enhanced_reply(
            email['subject'],
            email['body'], 
            email['sender'],
            email['thread_id']
        )
        
        logger.info(f"\nRESULTS:")
        logger.info(f"Classification: {classification}")
        logger.info(f"Documents: {docs}")
        logger.info(f"Reply Preview: {reply[:200]}...")
    
    logger.info(f"\n{'='*60}")
    logger.info("ENHANCED REPLY TESTING COMPLETE")
    logger.info(f"{'='*60}")