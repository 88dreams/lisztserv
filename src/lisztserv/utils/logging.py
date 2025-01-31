"""
Logging utilities for the lisztserv package.
"""
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from datetime import datetime
from typing import Optional, Tuple

def get_app_root():
    """Get the application root directory for both executable and development."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.dirname(sys.executable)
    else:
        # Running as script
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_log_dir():
    """Get the log directory path based on whether running as executable or script"""
    base_dir = get_app_root()
    log_dir = os.path.join(base_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    return log_dir

def setup_logging(log_level: str = "INFO", log_file: Optional[str] = None) -> Tuple[logging.Logger, logging.Logger]:
    """
    Set up logging configuration.
    
    Args:
        log_level: The logging level to use
        log_file: Optional path to a log file. If not provided, logs will be created in the default log directory
    
    Returns:
        Tuple of (main_logger, spotify_logger)
    """
    numeric_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Invalid log level: {log_level}')

    # Get log directory if log_file not specified
    if not log_file:
        log_dir = get_log_dir()
        os.makedirs(log_dir, exist_ok=True)
    else:
        log_dir = os.path.dirname(log_file)
        os.makedirs(log_dir, exist_ok=True)

    # Set up main logger
    logger = logging.getLogger('spot-main')
    logger.setLevel(numeric_level)
    logger.propagate = False  # Prevent propagation to root logger
    
    # Set up Spotify logger
    spotify_logger = logging.getLogger('spot-spotify')
    spotify_logger.setLevel(numeric_level)
    spotify_logger.propagate = False  # Prevent propagation to root logger

    # Create formatters
    console_formatter = logging.Formatter('%(levelname)s: %(message)s')
    file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s')

    # Console handlers
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    spotify_logger.addHandler(console_handler)

    # File handlers
    if log_file:
        main_handler = RotatingFileHandler(
            log_file,
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
    else:
        main_handler = logging.FileHandler(
            os.path.join(log_dir, f"spot-main-{datetime.now().strftime('%Y%m%d')}.log"),
            encoding='utf-8'
        )
        spotify_handler = logging.FileHandler(
            os.path.join(log_dir, f"spot-spotify-{datetime.now().strftime('%Y%m%d')}.log"),
            encoding='utf-8'
        )
        spotify_handler.setFormatter(file_formatter)
        spotify_logger.addHandler(spotify_handler)

    main_handler.setFormatter(file_formatter)
    logger.addHandler(main_handler)

    # Log initialization silently (only to file)
    logger.info(f"Logging initialized. Log directory: {log_dir}")
    if not log_file:
        spotify_logger.info(f"Spotify logging initialized. Log directory: {log_dir}")

    return logger, spotify_logger

def user_message(msg: str, log_only: bool = False) -> None:
    """
    Log a message and optionally display it to the user.
    
    Args:
        msg: The message to log
        log_only: If True, only log the message without printing to console
    """
    logger = logging.getLogger('spot-main')
    logger.info(msg)
    if not log_only:
        print(msg) 