import json
import os
import time
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional
from logger_config import get_logger, log_performance
from config_loader import config

# Initialize logger for this module
logger = get_logger("thread_manager")

# Load configuration values
MAX_THREAD_HISTORY = config.max_thread_history

logger.info(f"Thread manager initialized with max history: {MAX_THREAD_HISTORY}")


class StorageProvider(ABC):
    """Abstract base class for thread storage providers"""
    
    @abstractmethod
    def load_threads(self) -> Dict[str, List[Dict]]:
        """Load all thread data. Returns empty dict if no data exists."""
        pass
    
    @abstractmethod
    def save_threads(self, threads: Dict[str, List[Dict]]) -> bool:
        """Save all thread data. Returns True if successful."""
        pass
    
    @abstractmethod
    def get_thread_history(self, thread_id: str) -> List[Dict]:
        """Get conversation history for a specific thread."""
        pass
    
    @abstractmethod
    def add_email_to_thread(self, thread_id: str, email_data: Dict) -> bool:
        """Add an email to a thread's history. Returns True if successful."""
        pass
    
    @abstractmethod
    def cleanup_old_threads(self, days_old: int) -> int:
        """Remove threads older than specified days. Returns count removed."""
        pass
    
    @abstractmethod
    def get_storage_stats(self) -> Dict:
        """Get storage statistics for monitoring."""
        pass


class JSONStorageProvider(StorageProvider):
    """JSON file-based storage provider (current implementation)"""
    
    def __init__(self, file_path: Optional[str] = None):
        self.file_path = file_path or config.threads_file
        logger.info(f"JSON storage provider initialized with file: {self.file_path}")
    
    def load_threads(self) -> Dict[str, List[Dict]]:
        """Load thread history from JSON file"""
        start_time = time.time()
        
        if not os.path.exists(self.file_path):
            logger.info(f"JSON file {self.file_path} does not exist, returning empty thread dictionary")
            return {}
        
        try:
            logger.debug(f"Loading threads from: {self.file_path}")
            
            # Check file size for performance logging
            file_size = os.path.getsize(self.file_path)
            logger.debug(f"JSON file size: {file_size} bytes")
            
            with open(self.file_path, 'r', encoding='utf-8') as f:
                threads = json.load(f)
            
            duration = time.time() - start_time
            thread_count = len(threads)
            total_emails = sum(len(history) for history in threads.values())
            
            logger.info(f"Successfully loaded {thread_count} threads with {total_emails} total emails")
            log_performance(logger, "JSON load_threads", duration, thread_count)
            
            return threads
            
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error loading threads file: {e}")
            logger.warning("JSON file may be corrupted, backing up and returning empty dict")
            
            # Create backup of corrupted file
            backup_name = f"{self.file_path}.backup_{int(time.time())}"
            try:
                os.rename(self.file_path, backup_name)
                logger.info(f"Corrupted file backed up as: {backup_name}")
            except Exception as backup_error:
                logger.error(f"Failed to backup corrupted file: {backup_error}")
            
            return {}
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error loading JSON threads file after {duration:.2f}s: {e}")
            return {}
    
    def save_threads(self, threads: Dict[str, List[Dict]]) -> bool:
        """Save thread history to JSON file"""
        start_time = time.time()
        
        if not threads:
            logger.warning("Attempting to save empty threads dictionary")
        
        thread_count = len(threads)
        total_emails = sum(len(history) for history in threads.values())
        
        logger.debug(f"Saving {thread_count} threads with {total_emails} total emails")
        
        try:
            # Create temporary file first for atomic write
            temp_file = f"{self.file_path}.tmp"
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(threads, f, indent=2, ensure_ascii=False)
            
            # Atomic replace
            os.replace(temp_file, self.file_path)
            
            duration = time.time() - start_time
            file_size = os.path.getsize(self.file_path)
            
            logger.info(f"Successfully saved {thread_count} threads to JSON file")
            logger.debug(f"File size: {file_size} bytes")
            log_performance(logger, "JSON save_threads", duration, thread_count)
            
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error saving JSON threads file after {duration:.2f}s: {e}")
            
            # Clean up temp file if it exists
            temp_file = f"{self.file_path}.tmp"
            if os.path.exists(temp_file):
                try:
                    os.remove(temp_file)
                    logger.debug("Cleaned up temporary file after save failure")
                except Exception as cleanup_error:
                    logger.warning(f"Failed to clean up temporary file: {cleanup_error}")
            
            return False
    
    def get_thread_history(self, thread_id: str) -> List[Dict]:
        """Get conversation history for a specific thread"""
        if not thread_id:
            logger.warning("Empty thread_id provided to get_thread_history")
            return []
        
        logger.debug(f"Getting history for thread: {thread_id}")
        
        threads = self.load_threads()
        history = threads.get(thread_id, [])
        
        if history:
            logger.debug(f"Found {len(history)} emails in thread {thread_id}")
        else:
            logger.debug(f"No history found for thread {thread_id}")
        
        return history
    
    def add_email_to_thread(self, thread_id: str, email_data: Dict) -> bool:
        """Add an email to a thread's conversation history"""
        start_time = time.time()
        
        if not thread_id:
            logger.error("Empty thread_id provided to add_email_to_thread")
            return False
        
        try:
            threads = self.load_threads()
            
            # Create thread if it doesn't exist
            if thread_id not in threads:
                logger.info(f"Creating new thread: {thread_id}")
                threads[thread_id] = []
            
            # Add to thread
            threads[thread_id].append(email_data)
            new_count = len(threads[thread_id])
            logger.debug(f"Thread {thread_id} now has {new_count} emails")
            
            # Trim to keep only last MAX_THREAD_HISTORY emails
            if new_count > MAX_THREAD_HISTORY:
                emails_to_remove = new_count - MAX_THREAD_HISTORY
                logger.info(f"Thread {thread_id}: Trimming {emails_to_remove} old emails (keeping last {MAX_THREAD_HISTORY})")
                threads[thread_id] = threads[thread_id][-MAX_THREAD_HISTORY:]
                logger.debug(f"Thread {thread_id} trimmed to {len(threads[thread_id])} emails")
            
            # Save updated threads
            save_success = self.save_threads(threads)
            if not save_success:
                logger.error(f"Failed to save threads after adding email to {thread_id}")
                return False
            
            duration = time.time() - start_time
            log_performance(logger, "JSON add_email_to_thread", duration, 1)
            
            return True
            
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error adding email to JSON thread {thread_id} after {duration:.2f}s: {e}")
            return False
    
    def cleanup_old_threads(self, days_old: int = 30) -> int:
        """Remove threads older than specified days"""
        logger.info(f"Starting JSON cleanup of threads older than {days_old} days")
        
        try:
            threads = self.load_threads()
            if not threads:
                logger.info("No threads to clean up")
                return 0
            
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days_old)
            cutoff_iso = cutoff_date.isoformat()
            
            threads_to_remove = []
            
            for thread_id, history in threads.items():
                if not history:
                    logger.debug(f"Thread {thread_id} is empty, marking for removal")
                    threads_to_remove.append(thread_id)
                    continue
                
                # Check the newest email in the thread
                newest_email = max(history, key=lambda x: x.get('timestamp', ''))
                newest_timestamp = newest_email.get('timestamp', '')
                
                if newest_timestamp < cutoff_iso:
                    logger.debug(f"Thread {thread_id} last activity: {newest_timestamp}, marking for removal")
                    threads_to_remove.append(thread_id)
            
            # Remove old threads
            removed_count = 0
            for thread_id in threads_to_remove:
                del threads[thread_id]
                removed_count += 1
                logger.debug(f"Removed old thread: {thread_id}")
            
            if removed_count > 0:
                save_success = self.save_threads(threads)
                if save_success:
                    logger.info(f"Successfully cleaned up {removed_count} old threads")
                else:
                    logger.error("Failed to save threads after cleanup")
                    return 0
            else:
                logger.info("No old threads found to clean up")
            
            return removed_count
            
        except Exception as e:
            logger.error(f"Error during JSON thread cleanup: {e}")
            return 0
    
    def get_storage_stats(self) -> Dict:
        """Get JSON storage statistics"""
        try:
            threads = self.load_threads()
            
            if not threads:
                return {
                    "provider_type": "JSON",
                    "file_path": self.file_path,
                    "file_exists": os.path.exists(self.file_path),
                    "file_size_bytes": 0,
                    "total_threads": 0,
                    "total_emails": 0,
                    "threads_with_history": 0,
                    "avg_emails_per_thread": 0,
                    "threads_at_limit": 0,
                    "bot_replies": 0,
                    "user_emails": 0
                }
            
            total_threads = len(threads)
            total_emails = sum(len(history) for history in threads.values())
            threads_with_history = len([t for t in threads.values() if len(t) > 1])
            threads_at_limit = len([t for t in threads.values() if len(t) >= MAX_THREAD_HISTORY])
            
            bot_replies = 0
            user_emails = 0
            
            for history in threads.values():
                for email in history:
                    if email.get("is_bot_reply", False):
                        bot_replies += 1
                    else:
                        user_emails += 1
            
            avg_emails_per_thread = total_emails / total_threads if total_threads > 0 else 0
            file_size = os.path.getsize(self.file_path) if os.path.exists(self.file_path) else 0
            
            return {
                "provider_type": "JSON",
                "file_path": self.file_path,
                "file_exists": os.path.exists(self.file_path),
                "file_size_bytes": file_size,
                "total_threads": total_threads,
                "total_emails": total_emails,
                "threads_with_history": threads_with_history,
                "avg_emails_per_thread": round(avg_emails_per_thread, 1),
                "threads_at_limit": threads_at_limit,
                "bot_replies": bot_replies,
                "user_emails": user_emails
            }
            
        except Exception as e:
            logger.error(f"Error calculating JSON storage statistics: {e}")
            return {"provider_type": "JSON", "error": str(e)}


class SQLiteStorageProvider(StorageProvider):
    """SQLite database storage provider for better performance and scalability"""
    
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or config.get("storage.sqlite_path", "email_threads.db")
        logger.info(f"SQLite storage provider initialized with database: {self.db_path}")
        self._initialize_database()
    
    def _initialize_database(self):
        """Create database tables if they don't exist"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    CREATE TABLE IF NOT EXISTS threads (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        thread_id TEXT NOT NULL,
                        uid INTEGER,
                        sender TEXT NOT NULL,
                        subject TEXT NOT NULL,
                        body TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        is_bot_reply BOOLEAN NOT NULL DEFAULT 0,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_thread_id ON threads(thread_id)
                ''')
                conn.execute('''
                    CREATE INDEX IF NOT EXISTS idx_timestamp ON threads(timestamp)
                ''')
                conn.commit()
                logger.info("SQLite database initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing SQLite database: {e}")
            raise

    def load_threads(self) -> Dict[str, List[Dict]]:
        """Load all thread data from SQLite"""
        start_time = time.time()
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT thread_id, uid, sender, subject, body, timestamp, is_bot_reply
                    FROM threads
                    ORDER BY thread_id, timestamp
                ''')
                threads = {}
                for row in cursor:
                    thread_id = row['thread_id']
                    if thread_id not in threads:
                        threads[thread_id] = []
                    email_data = {
                        'uid': row['uid'],
                        'sender': row['sender'],
                        'subject': row['subject'],
                        'body': row['body'],
                        'timestamp': row['timestamp'],
                        'is_bot_reply': bool(row['is_bot_reply'])
                    }
                    threads[thread_id].append(email_data)
                duration = time.time() - start_time
                thread_count = len(threads)
                total_emails = sum(len(history) for history in threads.values())
                logger.info(f"Successfully loaded {thread_count} threads with {total_emails} total emails from SQLite")
                log_performance(logger, "SQLite load_threads", duration, thread_count)
                return threads
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error loading threads from SQLite after {duration:.2f}s: {e}")
            return {}

    def save_threads(self, threads: Dict[str, List[Dict]]) -> bool:
        """Save all thread data to SQLite (mainly for compatibility - prefer add_email_to_thread)"""
        logger.warning("save_threads() called on SQLite provider - this will recreate the entire database")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('DELETE FROM threads')
                for thread_id, history in threads.items():
                    for email in history:
                        conn.execute('''
                            INSERT INTO threads (thread_id, uid, sender, subject, body, timestamp, is_bot_reply)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            thread_id,
                            email.get('uid'),
                            email.get('sender', ''),
                            email.get('subject', ''),
                            email.get('body', ''),
                            email.get('timestamp', ''),
                            email.get('is_bot_reply', False)
                        ))
                conn.commit()
                total_emails = sum(len(history) for history in threads.values())
                logger.info(f"Successfully saved {len(threads)} threads with {total_emails} emails to SQLite")
                return True
        except Exception as e:
            logger.error(f"Error saving threads to SQLite: {e}")
            return False

    def get_thread_history(self, thread_id: str) -> List[Dict]:
        """Get conversation history for a specific thread from SQLite"""
        if not thread_id:
            logger.warning("Empty thread_id provided to get_thread_history")
            return []
        logger.debug(f"Getting SQLite history for thread: {thread_id}")
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute('''
                    SELECT uid, sender, subject, body, timestamp, is_bot_reply
                    FROM threads
                    WHERE thread_id = ?
                    ORDER BY timestamp
                    LIMIT ?
                ''', (thread_id, MAX_THREAD_HISTORY))
                history = []
                for row in cursor:
                    email_data = {
                        'uid': row['uid'],
                        'sender': row['sender'],
                        'subject': row['subject'],
                        'body': row['body'],
                        'timestamp': row['timestamp'],
                        'is_bot_reply': bool(row['is_bot_reply'])
                    }
                    history.append(email_data)
                if history:
                    logger.debug(f"Found {len(history)} emails in SQLite thread {thread_id}")
                else:
                    logger.debug(f"No history found for SQLite thread {thread_id}")
                return history
        except Exception as e:
            logger.error(f"Error getting SQLite thread history for {thread_id}: {e}")
            return []

    def add_email_to_thread(self, thread_id: str, email_data: Dict) -> bool:
        """Add an email to a thread's conversation history in SQLite"""
        start_time = time.time()
        if not thread_id:
            logger.error("Empty thread_id provided to add_email_to_thread")
            return False
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute('''
                    INSERT INTO threads (thread_id, uid, sender, subject, body, timestamp, is_bot_reply)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    thread_id,
                    email_data.get('uid'),
                    email_data.get('sender', ''),
                    email_data.get('subject', ''),
                    email_data.get('body', ''),
                    email_data.get('timestamp', ''),
                    email_data.get('is_bot_reply', False)
                ))
                cursor = conn.execute('''
                    SELECT COUNT(*) as count FROM threads WHERE thread_id = ?
                ''', (thread_id,))
                count = cursor.fetchone()[0]
                if count > MAX_THREAD_HISTORY:
                    emails_to_remove = count - MAX_THREAD_HISTORY
                    logger.info(f"SQLite thread {thread_id}: Trimming {emails_to_remove} old emails")
                    conn.execute('''
                        DELETE FROM threads
                        WHERE thread_id = ?
                        AND id IN (
                            SELECT id FROM threads
                            WHERE thread_id = ?
                            ORDER BY timestamp
                            LIMIT ?
                        )
                    ''', (thread_id, thread_id, emails_to_remove))
                conn.commit()
                duration = time.time() - start_time
                log_performance(logger, "SQLite add_email_to_thread", duration, 1)
                return True
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Error adding email to SQLite thread {thread_id} after {duration:.2f}s: {e}")
            return False

    def cleanup_old_threads(self, days_old: int = 30) -> int:
        """Remove threads older than specified days from SQLite"""
        logger.info(f"Starting SQLite cleanup of threads older than {days_old} days")
        try:
            from datetime import timedelta
            cutoff_date = datetime.now() - timedelta(days=days_old)
            cutoff_iso = cutoff_date.isoformat()
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute('''
                    SELECT DISTINCT thread_id FROM threads
                    WHERE thread_id IN (
                        SELECT thread_id FROM threads
                        GROUP BY thread_id
                        HAVING MAX(timestamp) < ?
                    )
                ''', (cutoff_iso,))
                threads_to_remove = [row[0] for row in cursor.fetchall()]
                if threads_to_remove:
                    placeholders = ','.join('?' * len(threads_to_remove))
                    cursor = conn.execute(f'''
                        DELETE FROM threads WHERE thread_id IN ({placeholders})
                    ''', threads_to_remove)
                    removed_count = cursor.rowcount
                    conn.commit()
                    logger.info(f"Successfully cleaned up {removed_count} emails from {len(threads_to_remove)} old threads")
                    return len(threads_to_remove)
                else:
                    logger.info("No old threads found to clean up")
                    return 0
        except Exception as e:
            logger.error(f"Error during SQLite thread cleanup: {e}")
            return 0

    def get_storage_stats(self) -> Dict:
        """Get SQLite storage statistics"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Basic counts
                cursor = conn.execute('SELECT COUNT(DISTINCT thread_id) FROM threads')
                total_threads = cursor.fetchone()[0]
                
                cursor = conn.execute('SELECT COUNT(*) FROM threads')
                total_emails = cursor.fetchone()[0]
                
                cursor = conn.execute('''
                    SELECT COUNT(DISTINCT thread_id) FROM threads
                    GROUP BY thread_id
                    HAVING COUNT(*) > 1
                ''')
                threads_with_history = len(cursor.fetchall())
                
                cursor = conn.execute('''
                    SELECT COUNT(DISTINCT thread_id) FROM threads
                    GROUP BY thread_id
                    HAVING COUNT(*) >= ?
                ''', (MAX_THREAD_HISTORY,))
                threads_at_limit = len(cursor.fetchall())
                
                cursor = conn.execute('SELECT COUNT(*) FROM threads WHERE is_bot_reply = 1')
                bot_replies = cursor.fetchone()[0]
                
                user_emails = total_emails - bot_replies
                avg_emails_per_thread = total_emails / total_threads if total_threads > 0 else 0
                
                # Database file size
                db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                
                return {
                    "provider_type": "SQLite",
                    "database_path": self.db_path,
                    "database_exists": os.path.exists(self.db_path),
                    "database_size_bytes": db_size,
                    "total_threads": total_threads,
                    "total_emails": total_emails,
                    "threads_with_history": threads_with_history,
                    "avg_emails_per_thread": round(avg_emails_per_thread, 1),
                    "threads_at_limit": threads_at_limit,
                    "bot_replies": bot_replies,
                    "user_emails": user_emails
                }
                
        except Exception as e:
            logger.error(f"Error calculating SQLite storage statistics: {e}")
            return {"provider_type": "SQLite", "error": str(e)}


class MockStorageProvider(StorageProvider):
    """In-memory mock storage provider for testing"""
    
    def __init__(self):
        logger.info("Mock storage provider initialized")
        self.threads = {}
        self.operation_count = 0
    
    def load_threads(self) -> Dict[str, List[Dict]]:
        """Return in-memory threads"""
        self.operation_count += 1
        logger.debug(f"Mock load_threads called (operation #{self.operation_count})")
        return self.threads.copy()
    
    def save_threads(self, threads: Dict[str, List[Dict]]) -> bool:
        """Save to in-memory storage"""
        self.operation_count += 1
        logger.debug(f"Mock save_threads called with {len(threads)} threads (operation #{self.operation_count})")
        self.threads = threads.copy()
        return True
    
    def get_thread_history(self, thread_id: str) -> List[Dict]:
        """Get thread history from memory"""
        self.operation_count += 1
        logger.debug(f"Mock get_thread_history for {thread_id} (operation #{self.operation_count})")
        return self.threads.get(thread_id, []).copy()
    
    def add_email_to_thread(self, thread_id: str, email_data: Dict) -> bool:
        """Add email to in-memory thread"""
        self.operation_count += 1
        logger.debug(f"Mock add_email_to_thread for {thread_id} (operation #{self.operation_count})")
        
        if thread_id not in self.threads:
            self.threads[thread_id] = []
        
        self.threads[thread_id].append(email_data.copy())
        
        # Trim if necessary
        if len(self.threads[thread_id]) > MAX_THREAD_HISTORY:
            self.threads[thread_id] = self.threads[thread_id][-MAX_THREAD_HISTORY:]
        
        return True
    
    def cleanup_old_threads(self, days_old: int = 30) -> int:
        """Mock cleanup - removes threads with 'old' in the name"""
        self.operation_count += 1
        logger.debug(f"Mock cleanup_old_threads (operation #{self.operation_count})")
        
        old_threads = [tid for tid in self.threads.keys() if 'old' in tid.lower()]
        for tid in old_threads:
            del self.threads[tid]
        
        logger.info(f"Mock cleanup removed {len(old_threads)} 'old' threads")
        return len(old_threads)
    
    def get_storage_stats(self) -> Dict:
        """Get mock storage statistics"""
        total_threads = len(self.threads)
        total_emails = sum(len(history) for history in self.threads.values())
        
        return {
            "provider_type": "Mock",
            "operation_count": self.operation_count,
            "total_threads": total_threads,
            "total_emails": total_emails,
            "threads_with_history": len([t for t in self.threads.values() if len(t) > 1]),
            "avg_emails_per_thread": total_emails / total_threads if total_threads > 0 else 0,
            "threads_at_limit": len([t for t in self.threads.values() if len(t) >= MAX_THREAD_HISTORY]),
            "bot_replies": sum(sum(1 for e in history if e.get("is_bot_reply", False)) for history in self.threads.values()),
            "user_emails": sum(sum(1 for e in history if not e.get("is_bot_reply", False)) for history in self.threads.values())
        }


def get_storage_provider() -> StorageProvider:
    """Factory function to get the appropriate storage provider based on configuration"""
    provider_type = config.get("storage.provider", "json").lower()
    
    logger.info(f"Initializing storage provider: {provider_type}")
    
    if provider_type == "json":
        return JSONStorageProvider()
    elif provider_type == "sqlite":
        return SQLiteStorageProvider()
    elif provider_type == "mock":
        return MockStorageProvider()
    else:
        logger.error(f"Unknown storage provider type: {provider_type}")
        logger.info("Falling back to JSON storage provider")
        return JSONStorageProvider()


# Initialize the storage provider
try:
    storage_provider = get_storage_provider()
    logger.info(f"Storage provider initialized successfully: {type(storage_provider).__name__}")
except Exception as e:
    logger.critical(f"Failed to initialize storage provider: {e}")
    raise


# Public API functions (maintain backward compatibility)
def load_threads() -> Dict[str, List[Dict]]:
    """Load thread history using the configured storage provider"""
    return storage_provider.load_threads()


def save_threads(threads: Dict[str, List[Dict]]) -> bool:
    """Save thread history using the configured storage provider"""
    return storage_provider.save_threads(threads)


def get_thread_history(thread_id: str) -> List[Dict]:
    """Get conversation history for a specific thread"""
    return storage_provider.get_thread_history(thread_id)


def add_email_to_thread(thread_id: str, sender: str, subject: str, body: str, uid: Optional[int] = None, is_bot_reply: bool = False) -> bool:
    """Add an email to a thread's conversation history"""
    email_type = "bot reply" if is_bot_reply else "user email"
    logger.info(f"Adding {email_type} to thread {thread_id} using {type(storage_provider).__name__}")
    
    email_data = {
        "uid": uid,
        "sender": sender,
        "subject": subject,
        "body": body,
        "timestamp": datetime.now().isoformat(),
        "is_bot_reply": is_bot_reply
    }
    
    return storage_provider.add_email_to_thread(thread_id, email_data)


def format_thread_context(thread_history: List[Dict]) -> str:
    """Format thread history into a readable context string for AI"""
    if not thread_history:
        logger.debug("No thread history provided to format_thread_context")
        return ""
    
    logger.debug(f"Formatting context for {len(thread_history)} emails")
    
    try:
        context_lines = ["Here is the conversation history:"]
        
        bot_count = 0
        user_count = 0
        
        for i, email in enumerate(thread_history):
            is_bot = email.get("is_bot_reply", False)
            sender_label = "Bot" if is_bot else email.get("sender", "Unknown")
            
            if is_bot:
                bot_count += 1
            else:
                user_count += 1
            
            context_lines.append(f"\nFrom: {sender_label}")
            context_lines.append(f"Subject: {email.get('subject', 'No subject')}")
            context_lines.append(f"Message: {email.get('body', 'No content')}")
            context_lines.append("-" * 40)
        
        context_lines.append("\nNow please reply to the latest email below:")
        formatted_context = "\n".join(context_lines)
        
        logger.debug(f"Formatted context: {len(formatted_context)} characters")
        logger.debug(f"Context includes {user_count} user emails and {bot_count} bot replies")
        
        return formatted_context
        
    except Exception as e:
        logger.error(f"Error formatting thread context: {e}")
        return ""


def get_thread_stats() -> Dict:
    """Get basic stats about stored threads using the configured storage provider"""
    logger.debug("Calculating thread statistics")
    return storage_provider.get_storage_stats()


def cleanup_old_threads(days_old: int = 30) -> int:
    """Remove threads older than specified days using the configured storage provider"""
    return storage_provider.cleanup_old_threads(days_old)


if __name__ == "__main__":
    from logger_config import setup_logging
    
    # Enable debug logging for testing
    setup_logging(log_level="DEBUG")
    
    logger.info("Testing thread manager with storage provider abstraction...")
    
    current_provider = type(storage_provider).__name__
    logger.info(f"Using storage provider: {current_provider}")
    
    # Test adding emails to a thread
    logger.info("Adding test emails to thread_123:")
    add_email_to_thread("thread_123", "customer@test.com", "Product Question", "What are your specs?", 101, False)
    add_email_to_thread("thread_123", "bot@company.com", "Re: Product Question", "Here are our specifications...", None, True)
    add_email_to_thread("thread_123", "customer@test.com", "Re: Product Question", "Thanks! What about pricing?", 102, False)
    
    # Test retrieving history
    logger.info("Retrieving thread history:")
    history = get_thread_history("thread_123")
    logger.info(f"Found {len(history)} emails in thread")
    
    for i, email in enumerate(history):
        email_type = "Bot reply" if email.get('is_bot_reply') else "User email"
        logger.info(f"{i+1}. {email_type} from: {email.get('sender')}")
        logger.info(f"   Subject: {email.get('subject')}")
        logger.info(f"   Body: {email.get('body', '')[:50]}...")
    
    # Test context formatting
    logger.info("Testing context formatting:")
    context = format_thread_context(history)
    logger.info(f"Generated context: {len(context)} characters")
    
    # Test stats
    logger.info("Getting thread statistics:")
    stats = get_thread_stats()
    for key, value in stats.items():
        logger.info(f"{key}: {value}")
    
    # Test cleanup (with 0 days to test the function)
    logger.info("Testing cleanup function:")
    removed = cleanup_old_threads(days_old=0)
    logger.info(f"Cleanup removed {removed} threads")
    
    # Test different providers if mock
    if current_provider == "MockStorageProvider":
        logger.info("Testing mock-specific features...")
        
        # Add some 'old' threads for cleanup testing
        add_email_to_thread("old_thread_1", "test@example.com", "Old Email", "This is old", 999, False)
        add_email_to_thread("old_thread_2", "test@example.com", "Another Old Email", "This is also old", 998, False)
        
        logger.info("Added test 'old' threads, running cleanup again:")
        removed = cleanup_old_threads(days_old=30)
        logger.info(f"Cleanup removed {removed} old threads")
        
        final_stats = get_thread_stats()
        logger.info(f"Final stats: {final_stats}")
    
    logger.info(f"\nStorage provider testing complete using {current_provider}!")
    logger.info("Check your storage (file/database) to see the stored data!")
