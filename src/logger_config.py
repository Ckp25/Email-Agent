import logging
import sys
import os
from datetime import datetime
from typing import Optional

# Color codes for console output
class LogColors:
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class ColoredFormatter(logging.Formatter):
    """Custom formatter that adds colors to log levels"""
    
    COLORS = {
        'DEBUG': LogColors.CYAN,
        'INFO': LogColors.GREEN,
        'WARNING': LogColors.YELLOW,
        'ERROR': LogColors.RED,
        'CRITICAL': LogColors.RED + LogColors.BOLD
    }

    def format(self, record):
        # Save the original format
        original_format = self._style._fmt
        
        # Add color to the log level
        color = self.COLORS.get(record.levelname, LogColors.WHITE)
        colored_levelname = f"{color}{record.levelname}{LogColors.RESET}"
        
        # Temporarily modify the record
        record.levelname = colored_levelname
        
        # Format the message
        formatted = super().format(record)
        
        # Restore original levelname for file logging
        record.levelname = record.levelname.replace(color, '').replace(LogColors.RESET, '')
        
        return formatted

# Global configuration
_loggers = {}
_log_level = logging.INFO
_log_to_file = False
_log_file_path = "email_bot.log"
_console_colors = True

def setup_logging(
    log_level: str = "INFO",
    log_to_file: bool = False,
    log_file_path: str = "email_bot.log",
    console_colors: bool = True,
    max_file_size_mb: int = 10,
    backup_count: int = 5
):
    """
    Configure global logging settings.
    
    Args:
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_to_file: Whether to log to file in addition to console
        log_file_path: Path to log file
        console_colors: Whether to use colors in console output
        max_file_size_mb: Maximum log file size before rotation
        backup_count: Number of backup log files to keep
    """
    global _log_level, _log_to_file, _log_file_path, _console_colors
    
    # Convert string level to logging constant
    level_map = {
        'DEBUG': logging.DEBUG,
        'INFO': logging.INFO,
        'WARNING': logging.WARNING,
        'ERROR': logging.ERROR,
        'CRITICAL': logging.CRITICAL
    }
    
    _log_level = level_map.get(log_level.upper(), logging.INFO)
    _log_to_file = log_to_file
    _log_file_path = log_file_path
    _console_colors = console_colors
    
    # Clear any existing loggers to reconfigure
    _loggers.clear()
    
    # Set up file logging if requested
    if _log_to_file:
        from logging.handlers import RotatingFileHandler
        
        # Create logs directory if it doesn't exist
        log_dir = os.path.dirname(_log_file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
        
        # Configure file handler with rotation
        file_handler = RotatingFileHandler(
            _log_file_path,
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count
        )
        file_handler.setLevel(_log_level)
        
        # File format (no colors)
        file_format = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        file_formatter = logging.Formatter(file_format, datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(file_formatter)
        
        # Add to root logger
        root_logger = logging.getLogger()
        root_logger.addHandler(file_handler)
        root_logger.setLevel(_log_level)

def get_logger(module_name: Optional[str] = None) -> logging.Logger:
    """
    Get a configured logger for the specified module.
    
    Args:
        module_name: Name of the module. If None, will try to detect automatically.
        
    Returns:
        Configured logger instance
    """
    # Auto-detect module name if not provided
    if module_name is None:
        import inspect
        frame = inspect.currentframe().f_back
        module_name = frame.f_globals.get('__name__', 'unknown')
        
        # Clean up module name (remove file extension, path)
        if module_name != '__main__':
            module_name = os.path.basename(module_name)
        else:
            # For main scripts, use the filename
            filename = frame.f_globals.get('__file__', 'main')
            module_name = os.path.splitext(os.path.basename(filename))[0]
    
    # Return cached logger if it exists
    if module_name in _loggers:
        return _loggers[module_name]
    
    # Create new logger
    logger = logging.getLogger(module_name)
    logger.setLevel(_log_level)
    
    # Remove any existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(_log_level)
    
    # Choose formatter based on color preference
    if _console_colors and sys.stdout.isatty():  # Only use colors if output is a terminal
        console_format = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        console_formatter = ColoredFormatter(console_format, datefmt='%H:%M:%S')
    else:
        console_format = "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        console_formatter = logging.Formatter(console_format, datefmt='%H:%M:%S')
    
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    # Prevent propagation to root logger to avoid duplicate messages
    logger.propagate = False
    
    # Cache the logger
    _loggers[module_name] = logger
    
    return logger

def log_email_operation(logger: logging.Logger, operation: str, count: int, details: str = ""):
    """
    Helper function for logging email operations with consistent format.
    
    Args:
        logger: Logger instance
        operation: Operation name (e.g., "fetched", "sent", "processed")
        count: Number of items
        details: Additional details
    """
    msg = f"Email operation: {operation} {count} email{'s' if count != 1 else ''}"
    if details:
        msg += f" - {details}"
    logger.info(msg)

def log_api_call(logger: logging.Logger, api_name: str, success: bool, details: str = ""):
    """
    Helper function for logging API calls.
    
    Args:
        logger: Logger instance
        api_name: Name of the API (e.g., "OpenAI", "Gmail")
        success: Whether the call was successful
        details: Additional details
    """
    level = logging.INFO if success else logging.ERROR
    status = "SUCCESS" if success else "FAILED"
    msg = f"API call: {api_name} - {status}"
    if details:
        msg += f" - {details}"
    logger.log(level, msg)

def log_batch_start(logger: logging.Logger, operation: str, count: int):
    """
    Helper function for logging batch operation start.
    
    Args:
        logger: Logger instance
        operation: Operation name
        count: Number of items in batch
    """
    logger.info(f"Starting batch {operation}: {count} item{'s' if count != 1 else ''}")

def log_batch_complete(logger: logging.Logger, operation: str, successful: int, failed: int):
    """
    Helper function for logging batch operation completion.
    
    Args:
        logger: Logger instance
        operation: Operation name
        successful: Number of successful items
        failed: Number of failed items
    """
    total = successful + failed
    success_rate = (successful / total * 100) if total > 0 else 0
    logger.info(f"Batch {operation} complete: {successful}/{total} successful ({success_rate:.1f}%)")
    
    if failed > 0:
        logger.warning(f"Batch {operation} had {failed} failure{'s' if failed != 1 else ''}")

def log_email_preview(logger: logging.Logger, sender: str, subject: str, body: str, max_body_length: int = 100):
    """
    Helper function for logging email content preview (for debugging).
    
    Args:
        logger: Logger instance
        sender: Email sender
        subject: Email subject
        body: Email body
        max_body_length: Maximum body length to log
    """
    body_preview = body[:max_body_length] + "..." if len(body) > max_body_length else body
    logger.debug(f"Email preview - From: {sender}, Subject: {subject}, Body: {body_preview}")

def log_performance(logger: logging.Logger, operation: str, duration_seconds: float, items_count: int = 1):
    """
    Helper function for logging performance metrics.
    
    Args:
        logger: Logger instance
        operation: Operation name
        duration_seconds: Time taken in seconds
        items_count: Number of items processed
    """
    rate = items_count / duration_seconds if duration_seconds > 0 else 0
    logger.info(f"Performance: {operation} took {duration_seconds:.2f}s for {items_count} item{'s' if items_count != 1 else ''} ({rate:.1f} items/sec)")

# Initialize with default settings - will be reconfigured when config is loaded
setup_logging()

if __name__ == "__main__":
    # Test the logging configuration
    print("Testing logging configuration...")
    
    # Test different modules
    test_logger = get_logger("test_module")
    mail_logger = get_logger("mail_reader")
    
    # Test different log levels
    test_logger.debug("This is a debug message")
    test_logger.info("This is an info message")
    test_logger.warning("This is a warning message")
    test_logger.error("This is an error message")
    test_logger.critical("This is a critical message")
    
    # Test helper functions
    log_email_operation(mail_logger, "fetched", 5, "from inbox")
    log_api_call(test_logger, "OpenAI", True, "generated reply in 1.2s")
    log_batch_start(mail_logger, "email processing", 3)
    log_batch_complete(mail_logger, "email processing", 2, 1)
    log_email_preview(test_logger, "test@example.com", "Test Subject", "This is a test email body that might be quite long and needs truncation")
    log_performance(test_logger, "email processing", 2.5, 3)
    
    print("\nTo enable file logging, call:")
    print('setup_logging(log_to_file=True, log_file_path="logs/email_bot.log")')
    
    print("\nTo change log level, call:")
    print('setup_logging(log_level="DEBUG")')