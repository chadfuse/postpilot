import os
import logging
import sys
from datetime import datetime
from typing import Optional
import json
from logging.handlers import RotatingFileHandler

class TikTokLogger:
    def __init__(self, name: str = "tiktok_collector", log_level: str = "INFO"):
        self.name = name
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.logger = None
        self.log_file = None
        self.setup_logger()
    
    def setup_logger(self):
        """Setup comprehensive logging system"""
        # Create logger
        self.logger = logging.getLogger(self.name)
        self.logger.setLevel(self.log_level)
        
        # Clear existing handlers
        self.logger.handlers.clear()
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(component)s - %(message)s'
        )
        
        simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(self.log_level)
        console_handler.setFormatter(simple_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler for general logs
        log_dir = os.getenv('LOG_PATH', '/logs')
        os.makedirs(log_dir, exist_ok=True)
        
        self.log_file = os.path.join(log_dir, 'system.log')
        file_handler = RotatingFileHandler(
            self.log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(file_handler)
        
        # Error file handler
        error_log_file = os.path.join(log_dir, 'errors.log')
        error_handler = RotatingFileHandler(
            error_log_file,
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(error_handler)
        
        # Debug file handler (only in debug mode)
        if os.getenv('DEBUG', 'false').lower() == 'true':
            debug_log_file = os.path.join(log_dir, 'debug.log')
            debug_handler = RotatingFileHandler(
                debug_log_file,
                maxBytes=20*1024*1024,  # 20MB
                backupCount=2,
                encoding='utf-8'
            )
            debug_handler.setLevel(logging.DEBUG)
            debug_handler.setFormatter(detailed_formatter)
            self.logger.addHandler(debug_handler)
    
    def log(self, level: str, component: str, message: str, details: Optional[str] = None, extra: Optional[dict] = None):
        """Log a message with component and optional details"""
        log_level = getattr(logging, level.upper(), logging.INFO)
        
        # Create log record with extra info
        extra_data = {
            'component': component,
            'details': details or '',
            **(extra or {})
        }
        
        # Format message
        if details:
            full_message = f"{message} | Details: {details}"
        else:
            full_message = message
        
        # Log the message
        self.logger.log(log_level, full_message, extra=extra_data)
        
        # Also log to database if available
        try:
            from .database import Database
            db = Database()
            
            if level.lower() == 'error':
                db.log_error(component, message, details)
            elif level.lower() == 'warning':
                db.log_warning(component, message, details)
            else:
                db.log_info(component, message, details)
        except Exception:
            # Avoid infinite recursion if database logging fails
            pass
    
    def info(self, component: str, message: str, details: Optional[str] = None, extra: Optional[dict] = None):
        """Log info message"""
        self.log('info', component, message, details, extra)
    
    def warning(self, component: str, message: str, details: Optional[str] = None, extra: Optional[dict] = None):
        """Log warning message"""
        self.log('warning', component, message, details, extra)
    
    def error(self, component: str, message: str, details: Optional[str] = None, extra: Optional[dict] = None):
        """Log error message"""
        self.log('error', component, message, details, extra)
    
    def debug(self, component: str, message: str, details: Optional[str] = None, extra: Optional[dict] = None):
        """Log debug message"""
        self.log('debug', component, message, details, extra)
    
    def critical(self, component: str, message: str, details: Optional[str] = None, extra: Optional[dict] = None):
        """Log critical message"""
        self.log('critical', component, message, details, extra)
    
    def log_api_request(self, method: str, endpoint: str, status_code: int, response_time: float, user_agent: str = None):
        """Log API request"""
        details = f"Method: {method}, Endpoint: {endpoint}, Status: {status_code}, Time: {response_time:.3f}s"
        if user_agent:
            details += f", User-Agent: {user_agent}"
        
        if status_code >= 400:
            self.error('api', f'API request failed: {method} {endpoint}', details)
        else:
            self.info('api', f'API request: {method} {endpoint}', details)
    
    def log_task_start(self, task_type: str, task_id: str, details: Optional[str] = None):
        """Log task start"""
        message = f"Task started: {task_type} (ID: {task_id})"
        self.info('task', message, details)
    
    def log_task_complete(self, task_type: str, task_id: str, duration: float, result: str = "success"):
        """Log task completion"""
        message = f"Task completed: {task_type} (ID: {task_id}) in {duration:.2f}s"
        details = f"Result: {result}"
        
        if result.lower() == "success":
            self.info('task', message, details)
        else:
            self.error('task', message, details)
    
    def log_task_error(self, task_type: str, task_id: str, error: str, duration: float = None):
        """Log task error"""
        message = f"Task failed: {task_type} (ID: {task_id})"
        details = f"Error: {error}"
        if duration is not None:
            details += f", Duration: {duration:.2f}s"
        
        self.error('task', message, details)
    
    def log_scraping_stats(self, keyword: str, videos_found: int, duration: float):
        """Log scraping statistics"""
        message = f"Scraping completed for keyword: {keyword}"
        details = f"Videos found: {videos_found}, Duration: {duration:.2f}s"
        self.info('scraper', message, details)
    
    def log_download_stats(self, videos_attempted: int, videos_downloaded: int, videos_failed: int, duration: float):
        """Log download statistics"""
        message = f"Download batch completed"
        details = f"Attempted: {videos_attempted}, Downloaded: {videos_downloaded}, Failed: {videos_failed}, Duration: {duration:.2f}s"
        self.info('downloader', message, details)
    
    def log_posting_stats(self, videos_attempted: int, videos_posted: int, videos_failed: int, duration: float):
        """Log posting statistics"""
        message = f"Posting batch completed"
        details = f"Attempted: {videos_attempted}, Posted: {videos_posted}, Failed: {videos_failed}, Duration: {duration:.2f}s"
        self.info('poster', message, details)
    
    def log_system_metrics(self, cpu_percent: float, memory_percent: float, disk_percent: float):
        """Log system metrics"""
        message = "System metrics"
        details = f"CPU: {cpu_percent:.1f}%, Memory: {memory_percent:.1f}%, Disk: {disk_percent:.1f}%"
        self.debug('system', message, details)
    
    def log_rate_limit(self, component: str, action: str, retry_after: int = None):
        """Log rate limiting"""
        message = f"Rate limit hit for {action}"
        details = f"Component: {component}"
        if retry_after:
            details += f", Retry after: {retry_after}s"
        
        self.warning('rate_limit', message, details)
    
    def log_security_event(self, event_type: str, details: str, severity: str = "warning"):
        """Log security events"""
        message = f"Security event: {event_type}"
        self.log(severity, 'security', message, details)
    
    def get_log_stats(self) -> dict:
        """Get logging statistics"""
        try:
            log_dir = os.getenv('LOG_PATH', '/logs')
            stats = {}
            
            # Check log files
            log_files = ['system.log', 'errors.log', 'debug.log']
            for log_file in log_files:
                file_path = os.path.join(log_dir, log_file)
                if os.path.exists(file_path):
                    size = os.path.getsize(file_path)
                    stats[log_file] = {
                        'size_bytes': size,
                        'size_mb': round(size / (1024 * 1024), 2),
                        'exists': True
                    }
                else:
                    stats[log_file] = {'exists': False}
            
            return stats
        except Exception as e:
            self.error('logger', f'Failed to get log stats: {str(e)}')
            return {}
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """Clean up old log files"""
        try:
            log_dir = os.getenv('LOG_PATH', '/logs')
            cutoff_time = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
            
            cleaned_files = 0
            cleaned_size = 0
            
            for filename in os.listdir(log_dir):
                if filename.endswith('.log') or filename.endswith('.log.1') or filename.endswith('.log.2'):
                    file_path = os.path.join(log_dir, filename)
                    if os.path.getmtime(file_path) < cutoff_time:
                        file_size = os.path.getsize(file_path)
                        os.remove(file_path)
                        cleaned_files += 1
                        cleaned_size += file_size
            
            message = f"Log cleanup completed"
            details = f"Files removed: {cleaned_files}, Space freed: {cleaned_size / (1024*1024):.2f}MB"
            self.info('logger', message, details)
            
            return {
                'files_removed': cleaned_files,
                'space_freed_mb': round(cleaned_size / (1024 * 1024), 2)
            }
        except Exception as e:
            self.error('logger', f'Log cleanup failed: {str(e)}')
            return {'files_removed': 0, 'space_freed_mb': 0}

# Global logger instance
logger = TikTokLogger()

# Convenience functions for direct import
def log_info(component: str, message: str, details: Optional[str] = None):
    """Log info message"""
    logger.info(component, message, details)

def log_warning(component: str, message: str, details: Optional[str] = None):
    """Log warning message"""
    logger.warning(component, message, details)

def log_error(component: str, message: str, details: Optional[str] = None):
    """Log error message"""
    logger.error(component, message, details)

def log_debug(component: str, message: str, details: Optional[str] = None):
    """Log debug message"""
    logger.debug(component, message, details)

def log_critical(component: str, message: str, details: Optional[str] = None):
    """Log critical message"""
    logger.critical(component, message, details)

# Decorator for automatic function logging
def log_function_calls(component: str = None):
    """Decorator to automatically log function calls"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            comp = component or func_name
            
            start_time = datetime.now()
            logger.debug(comp, f"Function started: {func_name}")
            
            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()
                logger.debug(comp, f"Function completed: {func_name}", f"Duration: {duration:.3f}s")
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                logger.error(comp, f"Function failed: {func_name}", f"Error: {str(e)}, Duration: {duration:.3f}s")
                raise
        
        return wrapper
    return decorator

# Context manager for operation logging
class OperationLogger:
    """Context manager for logging operations"""
    def __init__(self, component: str, operation: str, details: Optional[str] = None):
        self.component = component
        self.operation = operation
        self.details = details
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        logger.info(self.component, f"Operation started: {self.operation}", self.details)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        
        if exc_type is None:
            logger.info(self.component, f"Operation completed: {self.operation}", f"Duration: {duration:.2f}s")
        else:
            logger.error(self.component, f"Operation failed: {self.operation}", f"Error: {str(exc_val)}, Duration: {duration:.2f}s")
        
        return False  # Don't suppress exceptions
