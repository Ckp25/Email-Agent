import re
import time
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from logger_config import get_logger
from config_loader import config

# Initialize logger for this module
logger = get_logger("email_classifier")

@dataclass
class ClassificationResult:
    """Result of email classification"""
    primary_category: str
    confidence_score: float
    interest_level: str
    interest_score: int
    keywords_found: List[str]
    reasoning: str

class EmailClassifier:
    """Classifies emails by application type and interest level"""
    
    def __init__(self):
        logger.info("Email classifier initialized")
        
        # Define classification categories with keywords
        self.categories = {
            "coastal_erosion": {
                "keywords": [
                    # Primary coastal terms
                    "coastal", "coast", "shoreline", "beach", "seawall", "erosion",
                    "wave", "storm", "tide", "marine", "saltwater", "breakwater",
                    "revetment", "scour", "oceanfront", "waterfront", "embankment",
                    # Technical terms
                    "riprap", "armor stone", "geobag", "geotube", "slope protection",
                    "offshore", "nearshore", "littoral", "tsunami", "hurricane"
                ],
                "weight": 1.0,
                "description": "Coastal protection and erosion control applications"
            },
            
            "road_construction": {
                "keywords": [
                    # Road/highway terms
                    "road", "highway", "pavement", "asphalt", "concrete", "subgrade",
                    "base", "aggregate", "construction", "infrastructure", "traffic",
                    "separation", "stabilization", "embankment", "fill", "excavation",
                    # Technical terms
                    "cbr", "bearing capacity", "settlement", "compaction", "drainage",
                    "filter", "filtration", "aashto", "dot", "interstate", "bridge"
                ],
                "weight": 1.0,
                "description": "Road and highway construction applications"
            },
            
            "general_inquiry": {
                "keywords": [
                    # General business terms
                    "product", "catalog", "brochure", "company", "manufacturer",
                    "supplier", "price", "cost", "quote", "quotation", "information",
                    "details", "specification", "geotextile", "fabric", "material"
                ],
                "weight": 0.8,
                "description": "General product or company inquiries"
            }
        }
        
        # Interest level indicators
        self.interest_indicators = {
            "high_interest": {
                "keywords": [
                    # Buying signals
                    "project", "tender", "bid", "purchase", "order", "quantity",
                    "timeline", "deadline", "budget", "procurement", "contract",
                    "specification", "requirement", "urgent", "asap", "immediate",
                    # Project details
                    "site", "location", "area", "square meter", "sqm", "meter",
                    "ton", "tonne", "roll", "engineer", "consultant", "design"
                ],
                "score": 3,
                "description": "Strong buying signals or active projects"
            },
            
            "medium_interest": {
                "keywords": [
                    # Planning signals
                    "planning", "considering", "evaluation", "assessment", "study",
                    "feasibility", "proposal", "recommendation", "option", "solution",
                    "future", "upcoming", "potential", "possible", "interested"
                ],
                "score": 2,
                "description": "Planning or evaluation phase"
            },
            
            "surface_level": {
                "keywords": [
                    # General inquiries
                    "information", "general", "overview", "basic", "introduction",
                    "what", "how", "can you", "do you", "tell me", "explain",
                    "student", "research", "academic", "thesis", "study"
                ],
                "score": 1,
                "description": "Basic information seeking"
            }
        }
        
        logger.debug(f"Loaded {len(self.categories)} classification categories")
        logger.debug(f"Loaded {len(self.interest_indicators)} interest levels")
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text for analysis"""
        if not text:
            return ""
        
        # Convert to lowercase
        text = text.lower()
        
        # Remove email headers, signatures, etc.
        text = re.sub(r'(from:|to:|subject:|sent:|date:).*', '', text)
        text = re.sub(r'(best regards|sincerely|thanks|thank you).*', '', text)
        
        # Remove special characters but keep spaces
        text = re.sub(r'[^\w\s]', ' ', text)
        
        # Remove extra whitespace
        text = ' '.join(text.split())
        
        return text
    
    def extract_keywords(self, text: str, keyword_list: List[str]) -> List[str]:
        """Extract matching keywords from text"""
        found_keywords = []
        text_lower = text.lower()
        
        for keyword in keyword_list:
            # Check for whole word matches
            if re.search(r'\b' + re.escape(keyword.lower()) + r'\b', text_lower):
                found_keywords.append(keyword)
        
        return found_keywords
    
    def classify_by_category(self, text: str) -> Tuple[str, float, List[str]]:
        """Classify email into application category"""
        if not text.strip():
            return "general_inquiry", 0.1, []
        
        cleaned_text = self.clean_text(text)
        logger.debug(f"Analyzing text: {cleaned_text[:100]}...")
        
        category_scores = {}
        all_found_keywords = {}
        
        # Score each category
        for category, config in self.categories.items():
            found_keywords = self.extract_keywords(cleaned_text, config["keywords"])
            keyword_score = len(found_keywords) * config["weight"]
            
            category_scores[category] = keyword_score
            all_found_keywords[category] = found_keywords
            
            logger.debug(f"Category '{category}': {len(found_keywords)} keywords, score: {keyword_score}")
        
        # Find best category
        if not any(category_scores.values()):
            logger.debug("No category keywords found, defaulting to general_inquiry")
            return "general_inquiry", 0.1, []
        
        best_category = max(category_scores, key=category_scores.get)
        best_score = category_scores[best_category]
        
        # Normalize confidence score (0-1)
        max_possible_score = len(self.categories[best_category]["keywords"])
        confidence = min(best_score / max_possible_score, 1.0)
        
        found_keywords = all_found_keywords[best_category]
        
        logger.debug(f"Best category: {best_category} (confidence: {confidence:.2f})")
        return best_category, confidence, found_keywords
    
    def analyze_interest_level(self, text: str) -> Tuple[str, int, List[str]]:
        """Analyze interest level and buying signals"""
        if not text.strip():
            return "surface_level", 1, []
        
        cleaned_text = self.clean_text(text)
        total_score = 0
        all_found_keywords = []
        
        # Score interest indicators
        for interest_type, config in self.interest_indicators.items():
            found_keywords = self.extract_keywords(cleaned_text, config["keywords"])
            if found_keywords:
                score_contribution = len(found_keywords) * config["score"]
                total_score += score_contribution
                all_found_keywords.extend(found_keywords)
                
                logger.debug(f"Interest '{interest_type}': {len(found_keywords)} keywords, +{score_contribution} points")
        
        # Additional scoring factors
        text_length = len(cleaned_text.split())
        if text_length > 100:
            total_score += 1
            logger.debug(f"Long email bonus: +1 point (length: {text_length} words)")
        
        # Check for numbers (quantities, measurements, etc.)
        numbers = re.findall(r'\b\d+\b', cleaned_text)
        if numbers:
            total_score += min(len(numbers), 2)  # Max 2 points for numbers
            logger.debug(f"Numbers found: {numbers[:5]}... (+{min(len(numbers), 2)} points)")
        
        # Determine interest level
        if total_score >= 6:
            interest_level = "high_interest"
        elif total_score >= 3:
            interest_level = "medium_interest"
        else:
            interest_level = "surface_level"
        
        logger.debug(f"Interest analysis: {interest_level} (score: {total_score})")
        return interest_level, total_score, all_found_keywords
    
    def classify_email(self, subject: str, body: str, sender: str = "") -> ClassificationResult:
        """Classify email and return complete analysis"""
        start_time = time.time()
        
        logger.info(f"Classifying email from: {sender}")
        logger.debug(f"Subject: {subject}")
        logger.debug(f"Body length: {len(body)} characters")
        
        # Combine subject and body for analysis (subject gets more weight)
        combined_text = f"{subject} {subject} {body}"  # Subject counted twice for emphasis
        
        # Classify by category
        category, confidence, category_keywords = self.classify_by_category(combined_text)
        
        # Analyze interest level
        interest_level, interest_score, interest_keywords = self.analyze_interest_level(combined_text)
        
        # Combine all found keywords
        all_keywords = list(set(category_keywords + interest_keywords))
        
        # Generate reasoning
        reasoning_parts = []
        if category_keywords:
            reasoning_parts.append(f"Category '{category}' identified from keywords: {', '.join(category_keywords[:5])}")
        if interest_keywords:
            reasoning_parts.append(f"Interest level '{interest_level}' from signals: {', '.join(interest_keywords[:5])}")
        
        reasoning = ". ".join(reasoning_parts) if reasoning_parts else "Classification based on general patterns"
        
        # Create result
        result = ClassificationResult(
            primary_category=category,
            confidence_score=confidence,
            interest_level=interest_level,
            interest_score=interest_score,
            keywords_found=all_keywords,
            reasoning=reasoning
        )
        
        duration = time.time() - start_time
        
        logger.info(f"Classification complete in {duration:.3f}s:")
        logger.info(f"  Category: {category} (confidence: {confidence:.2f})")
        logger.info(f"  Interest: {interest_level} (score: {interest_score})")
        logger.info(f"  Keywords: {', '.join(all_keywords[:10])}")
        
        return result
    
    def should_flag_for_human_review(self, classification: ClassificationResult) -> bool:
        """Determine if email should be flagged for human review"""
        
        # High interest emails should be reviewed
        if classification.interest_level == "high_interest":
            logger.info("Flagging for human review: High interest level detected")
            return True
        
        # Medium interest with good category match
        if (classification.interest_level == "medium_interest" and 
            classification.confidence_score > 0.3):
            logger.info("Flagging for human review: Medium interest with good category match")
            return True
        
        # Very confident category classification might need specialist attention
        if classification.confidence_score > 0.7:
            logger.info("Flagging for human review: High confidence technical classification")
            return True
        
        logger.debug("No human review needed: Surface level inquiry")
        return False
    
    def get_recommended_documents(self, classification: ClassificationResult) -> List[str]:
        """Get document categories that match the classification"""
        category_to_docs = {
            "coastal_erosion": ["coastal", "erosion", "marine"],
            "road_construction": ["roads", "highways", "infrastructure"],
            "general_inquiry": ["general", "catalog", "products"]
        }
        
        recommended_categories = category_to_docs.get(
            classification.primary_category, 
            ["general", "catalog"]
        )
        
        logger.debug(f"Recommended document categories for {classification.primary_category}: {recommended_categories}")
        return recommended_categories


# Global classifier instance
try:
    email_classifier = EmailClassifier()
    logger.info("Global email classifier initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize email classifier: {e}")
    raise


# Public API functions
def classify_email(subject: str, body: str, sender: str = "") -> ClassificationResult:
    """Classify email and return complete analysis"""
    return email_classifier.classify_email(subject, body, sender)


def should_flag_for_human_review(classification: ClassificationResult) -> bool:
    """Determine if email should be flagged for human review"""
    return email_classifier.should_flag_for_human_review(classification)


def get_recommended_documents(classification: ClassificationResult) -> List[str]:
    """Get document categories that match the classification"""
    return email_classifier.get_recommended_documents(classification)


"""if __name__ == "__main__":
    from logger_config import setup_logging
    
    # Enable debug logging for testing
    setup_logging(log_level="DEBUG")
    
    logger.info("Testing email classifier...")
    
    # Test emails for different scenarios
    test_emails = [
        {
            "sender": "engineer@coastalproject.com",
            "subject": "Coastal protection for new seawall project",
            "body": "We are building a 500-meter seawall in Mumbai and need erosion control solutions. The project starts next month and we need geotextiles that can withstand wave action. Can you provide specifications and pricing for 2000 square meters?"
        },
        {
            "sender": "contractor@highways.com", 
            "subject": "Road construction materials needed",
            "body": "Our highway construction project requires separation fabric for subgrade stabilization. The soil has low CBR values and we need recommendations for 10,000 sqm. Project timeline is 6 months."
        },
        {
            "sender": "student@university.edu",
            "subject": "Information about geotextiles",
            "body": "Hi, I'm a civil engineering student doing research on geotextiles. Can you send me some general information about your products and applications?"
        },
        {
            "sender": "info@company.com",
            "subject": "Product inquiry", 
            "body": "Do you manufacture geotextiles? What products do you have available?"
        }
    ]
    
    logger.info(f"\n{'='*60}")
    logger.info("TESTING EMAIL CLASSIFICATION")
    logger.info(f"{'='*60}")
    
    for i, email in enumerate(test_emails, 1):
        logger.info(f"\n--- TEST EMAIL {i} ---")
        logger.info(f"From: {email['sender']}")
        logger.info(f"Subject: {email['subject']}")
        logger.info(f"Body: {email['body'][:100]}...")
        
        # Classify email
        result = classify_email(email['subject'], email['body'], email['sender'])
        
        # Check if needs human review
        needs_review = should_flag_for_human_review(result)
        
        # Get document recommendations
        doc_categories = get_recommended_documents(result)
        
        logger.info(f"\nRESULTS:")
        logger.info(f"  Category: {result.primary_category}")
        logger.info(f"  Confidence: {result.confidence_score:.2f}")
        logger.info(f"  Interest Level: {result.interest_level}")
        logger.info(f"  Interest Score: {result.interest_score}")
        logger.info(f"  Human Review: {'YES' if needs_review else 'NO'}")
        logger.info(f"  Recommended Docs: {doc_categories}")
        logger.info(f"  Keywords Found: {', '.join(result.keywords_found[:10])}")
        logger.info(f"  Reasoning: {result.reasoning}")
    
    logger.info(f"\n{'='*60}")
    logger.info("EMAIL CLASSIFICATION TESTING COMPLETE")
    logger.info(f"{'='*60}")"""