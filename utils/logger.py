"""
Logger module for SmartBoot

This module provides logging functionality for the application.
"""

import os
import logging
from logging.handlers import RotatingFileHandler
import platform
import datetime


class Logger:
    """
    Class for handling application logging.
    """
    
    def __init__(self, name="smartboot", log_level=logging.INFO):
        """
        Initialize the logger.
        
        Args:
            name (str): Logger name
            log_level (int): Logging level
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(log_level)
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(log_level)
        console_handler.setFormatter(formatter)
        
        # Create file handler
        log_dir = self._get_log_directory()
        os.makedirs(log_dir, exist_ok=True)
        
        log_file = os.path.join(log_dir, "smartboot.log")
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5*1024*1024, backupCount=5
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        
        # Add handlers to logger
        self.logger.addHandler(console_handler)
        self.logger.addHandler(file_handler)
        
        self.logger.info(f"Logger initialized at {datetime.datetime.now()}")
        self.logger.info(f"System: {platform.system()} {platform.release()}")
    
    def _get_log_directory(self):
        """
        Get the directory for log files based on the operating system.
        
        Returns:
            str: Path to log directory
        """
        system = platform.system()
        
        if system == "Windows":
            return os.path.join(os.environ.get("APPDATA", ""), "SmartBoot", "logs")
        elif system == "Linux":
            return os.path.join(os.path.expanduser("~"), ".smartboot", "logs")
        elif system == "Darwin":  # macOS
            return os.path.join(os.path.expanduser("~"), "Library", "Logs", "SmartBoot")
        else:
            return os.path.join(os.path.expanduser("~"), "smartboot_logs")
    
    def get_logger(self):
        """
        Get the logger instance.
        
        Returns:
            logging.Logger: Logger instance
        """
        return self.logger


# Create a default logger instance
default_logger = Logger().get_logger()


def get_logger():
    """
    Get the default logger instance.
    
    Returns:
        logging.Logger: Logger instance
    """
    return default_logger
