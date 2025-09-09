import json
import os
from typing import Dict, List, Optional, Tuple
from logger_config import get_logger
from config_loader import config

# Initialize logger for this module
logger = get_logger("document_manager")

class DocumentManager:
    """Manages document library for intelligent attachment system"""
    
    def __init__(self, documents_dir: str = None, library_file: str = None):
        # Use config or default paths
        self.documents_dir = documents_dir or config.get("documents.storage_path", "documents")
        self.library_file = library_file or config.get("documents.library_file", "document_library.json")
        self.library_path = os.path.join(self.documents_dir, self.library_file)
        
        logger.info(f"Document manager initialized")
        logger.debug(f"Documents directory: {self.documents_dir}")
        logger.debug(f"Library file: {self.library_path}")
        
        self.document_library = {}
        self.load_document_library()
    
    def load_document_library(self) -> bool:
        """Load document metadata from JSON file"""
        try:
            if not os.path.exists(self.library_path):
                logger.error(f"Document library not found: {self.library_path}")
                logger.info("Please ensure document_library.json exists in documents folder")
                return False
            
            logger.debug(f"Loading document library from: {self.library_path}")
            
            with open(self.library_path, 'r', encoding='utf-8') as f:
                self.document_library = json.load(f)
            
            document_count = len(self.document_library)
            logger.info(f"Successfully loaded {document_count} documents from library")
            
            # Validate that actual files exist
            missing_files = []
            for filename in self.document_library.keys():
                file_path = os.path.join(self.documents_dir, filename)
                if not os.path.exists(file_path):
                    missing_files.append(filename)
                    logger.warning(f"Document file not found: {filename}")
            
            if missing_files:
                logger.warning(f"Missing {len(missing_files)} document files: {missing_files}")
            else:
                logger.info("All document files found and accessible")
            
            return True
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in document library: {e}")
            return False
        except Exception as e:
            logger.error(f"Error loading document library: {e}")
            return False
    
    def get_all_documents(self) -> Dict:
        """Get all documents with their metadata"""
        logger.debug(f"Returning {len(self.document_library)} documents")
        return self.document_library.copy()
    
    def search_documents_by_category(self, categories: List[str]) -> List[Dict]:
        """Search documents that match any of the provided categories"""
        if not categories:
            logger.debug("No categories provided for search")
            return []
        
        logger.debug(f"Searching documents by categories: {categories}")
        
        matching_docs = []
        categories_lower = [cat.lower() for cat in categories]
        
        for filename, doc_info in self.document_library.items():
            doc_categories = [cat.lower() for cat in doc_info.get('categories', [])]
            doc_applications = [app.lower() for app in doc_info.get('applications', [])]
            doc_best_for = [bf.lower() for bf in doc_info.get('best_for', [])]
            
            # Check if any search category matches document categories, applications, or best_for
            all_doc_tags = doc_categories + doc_applications + doc_best_for
            
            if any(search_cat in all_doc_tags for search_cat in categories_lower):
                doc_result = doc_info.copy()
                doc_result['filename'] = filename
                doc_result['file_path'] = os.path.join(self.documents_dir, filename)
                matching_docs.append(doc_result)
                logger.debug(f"Found matching document: {filename}")
        
        logger.info(f"Found {len(matching_docs)} documents matching categories: {categories}")
        return matching_docs
    
    def search_documents_by_keywords(self, keywords: List[str]) -> List[Dict]:
        """Search documents by keywords in description and categories"""
        if not keywords:
            logger.debug("No keywords provided for search")
            return []
        
        logger.debug(f"Searching documents by keywords: {keywords}")
        
        matching_docs = []
        keywords_lower = [kw.lower() for kw in keywords]
        
        for filename, doc_info in self.document_library.items():
            # Search in description, display_name, categories, and applications
            searchable_text = " ".join([
                doc_info.get('description', '').lower(),
                doc_info.get('display_name', '').lower(),
                " ".join(doc_info.get('categories', [])).lower(),
                " ".join(doc_info.get('applications', [])).lower()
            ])
            
            # Check if any keyword appears in searchable text
            if any(keyword in searchable_text for keyword in keywords_lower):
                doc_result = doc_info.copy()
                doc_result['filename'] = filename
                doc_result['file_path'] = os.path.join(self.documents_dir, filename)
                matching_docs.append(doc_result)
                logger.debug(f"Found matching document: {filename}")
        
        logger.info(f"Found {len(matching_docs)} documents matching keywords: {keywords}")
        return matching_docs
    
    def get_document_by_filename(self, filename: str) -> Optional[Dict]:
        """Get specific document information by filename"""
        logger.debug(f"Looking up document: {filename}")
        
        if filename not in self.document_library:
            logger.warning(f"Document not found in library: {filename}")
            return None
        
        doc_info = self.document_library[filename].copy()
        doc_info['filename'] = filename
        doc_info['file_path'] = os.path.join(self.documents_dir, filename)
        
        # Check if file actually exists
        if not os.path.exists(doc_info['file_path']):
            logger.error(f"Document file not found on disk: {filename}")
            return None
        
        logger.debug(f"Found document: {filename}")
        return doc_info
    
    def validate_document_files(self) -> Tuple[List[str], List[str]]:
        """Validate that all library documents exist as files"""
        logger.info("Validating document files...")
        
        found_files = []
        missing_files = []
        
        for filename in self.document_library.keys():
            file_path = os.path.join(self.documents_dir, filename)
            if os.path.exists(file_path):
                found_files.append(filename)
                logger.debug(f"File exists: {filename}")
            else:
                missing_files.append(filename)
                logger.warning(f"File missing: {filename}")
        
        logger.info(f"Validation complete: {len(found_files)} found, {len(missing_files)} missing")
        
        if missing_files:
            logger.error(f"Missing files: {missing_files}")
        
        return found_files, missing_files
    
    def get_documents_for_llm_selection(self) -> str:
        """Format document library for LLM to choose from"""
        logger.debug("Formatting documents for LLM selection")
        
        if not self.document_library:
            logger.warning("No documents available for LLM selection")
            return "No documents available."
        
        formatted_docs = []
        formatted_docs.append("Available documents for attachment:")
        
        for filename, doc_info in self.document_library.items():
            formatted_docs.append(f"\n{filename}:")
            formatted_docs.append(f"  Name: {doc_info.get('display_name', 'Unknown')}")
            formatted_docs.append(f"  Description: {doc_info.get('description', 'No description')}")
            formatted_docs.append(f"  Best for: {', '.join(doc_info.get('best_for', []))}")
            formatted_docs.append(f"  Size: {doc_info.get('file_size_mb', 'Unknown')} MB")
        
        result = "\n".join(formatted_docs)
        logger.debug(f"Formatted {len(self.document_library)} documents for LLM")
        return result
    
    def get_document_stats(self) -> Dict:
        """Get statistics about the document library"""
        if not self.document_library:
            return {
                "total_documents": 0,
                "total_size_mb": 0,
                "categories": [],
                "applications": []
            }
        
        total_size = sum(doc.get('file_size_mb', 0) for doc in self.document_library.values())
        
        all_categories = set()
        all_applications = set()
        
        for doc_info in self.document_library.values():
            all_categories.update(doc_info.get('categories', []))
            all_applications.update(doc_info.get('applications', []))
        
        stats = {
            "total_documents": len(self.document_library),
            "total_size_mb": round(total_size, 1),
            "categories": sorted(list(all_categories)),
            "applications": sorted(list(all_applications)),
            "documents_dir": self.documents_dir,
            "library_file": self.library_path
        }
        
        logger.debug(f"Document stats: {stats}")
        return stats


# Global document manager instance
try:
    document_manager = DocumentManager()
    logger.info(f"Global document manager initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize document manager: {e}")
    raise


# Public API functions
def get_all_documents() -> Dict:
    """Get all documents with their metadata"""
    return document_manager.get_all_documents()


def search_documents_by_category(categories: List[str]) -> List[Dict]:
    """Search documents that match any of the provided categories"""
    return document_manager.search_documents_by_category(categories)


def search_documents_by_keywords(keywords: List[str]) -> List[Dict]:
    """Search documents by keywords in description and categories"""
    return document_manager.search_documents_by_keywords(keywords)


def get_document_by_filename(filename: str) -> Optional[Dict]:
    """Get specific document information by filename"""
    return document_manager.get_document_by_filename(filename)


def get_documents_for_llm_selection() -> str:
    """Format document library for LLM to choose from"""
    return document_manager.get_documents_for_llm_selection()


def validate_document_files() -> Tuple[List[str], List[str]]:
    """Validate that all library documents exist as files"""
    return document_manager.validate_document_files()


def get_document_stats() -> Dict:
    """Get statistics about the document library"""
    return document_manager.get_document_stats()


if __name__ == "__main__":
    from logger_config import setup_logging
    
    # Enable debug logging for testing
    setup_logging(log_level="DEBUG")
    
    logger.info("Testing document manager...")
    
    # Test loading documents
    logger.info("=== Document Library Stats ===")
    stats = get_document_stats()
    for key, value in stats.items():
        logger.info(f"{key}: {value}")
    
    # Test file validation
    logger.info("\n=== File Validation ===")
    found, missing = validate_document_files()
    logger.info(f"Found files: {found}")
    if missing:
        logger.warning(f"Missing files: {missing}")
    
    # Test category search
    logger.info("\n=== Category Search Tests ===")
    
    test_categories = [
        ["coastal", "erosion"],
        ["roads", "highway"],
        ["general", "catalog"],
        ["nonexistent"]
    ]
    
    for categories in test_categories:
        docs = search_documents_by_category(categories)
        logger.info(f"Search '{categories}': Found {len(docs)} documents")
        for doc in docs:
            logger.info(f"  - {doc['filename']}: {doc['display_name']}")
    
    # Test keyword search
    logger.info("\n=== Keyword Search Tests ===")
    
    test_keywords = [
        ["coastal", "protection"],
        ["road", "construction"],
        ["woven", "geotextile"],
        ["drainage", "filter"]
    ]
    
    for keywords in test_keywords:
        docs = search_documents_by_keywords(keywords)
        logger.info(f"Search '{keywords}': Found {len(docs)} documents")
        for doc in docs:
            logger.info(f"  - {doc['filename']}")
    
    # Test LLM formatting
    logger.info("\n=== LLM Selection Format ===")
    llm_format = get_documents_for_llm_selection()
    logger.info("LLM format preview:")
    logger.info(llm_format[:300] + "..." if len(llm_format) > 300 else llm_format)
    
    # Test individual document lookup
    logger.info("\n=== Individual Document Lookup ===")
    test_files = test_files = ["geotextile_catalog.pdf", "coastal_protection_guide.pdf", "nonexistent.pdf"]
    
    for filename in test_files:
        doc = get_document_by_filename(filename)
        if doc:
            logger.info(f"Found '{filename}': {doc['display_name']} ({doc['file_size_mb']} MB)")
        else:
            logger.warning(f"Not found: '{filename}'")
    
    logger.info("\nDocument manager testing complete!")