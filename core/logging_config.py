"""
Logging configuration for DhinSpeak System
path: core/logging_config.py
"""

import logging
import logging.handlers
import os
from pathlib import Path
from core.config import settings

def setup_logging():
    """Setup comprehensive logging configuration"""
    
    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, settings.LOG_LEVEL),
        format=settings.LOG_FORMAT,
        handlers=[
            logging.StreamHandler(),  # Console output
            logging.handlers.RotatingFileHandler(
                "logs/app.log",
                maxBytes=10*1024*1024,  # 10MB
                backupCount=5
            )
        ]
    )
    
    # Setup metrics logger (for research purposes)
    metrics_logger = logging.getLogger("metrics")
    metrics_logger.setLevel(logging.INFO)
    
    # Remove default handlers to avoid duplication
    metrics_logger.handlers.clear()
    metrics_logger.propagate = False
    
    # Add metrics-specific handler
    metrics_handler = logging.handlers.RotatingFileHandler(
        settings.METRICS_LOG_FILE,
        maxBytes=50*1024*1024,  # 50MB for metrics
        backupCount=10
    )
    
    # Custom format for metrics
    metrics_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    metrics_handler.setFormatter(metrics_formatter)
    metrics_logger.addHandler(metrics_handler)
    
    # Setup performance logger
    perf_logger = logging.getLogger("performance")
    perf_logger.setLevel(logging.INFO)
    perf_logger.handlers.clear()
    perf_logger.propagate = False
    
    perf_handler = logging.handlers.RotatingFileHandler(
        "logs/performance.log",
        maxBytes=20*1024*1024,  # 20MB
        backupCount=5
    )
    perf_handler.setFormatter(metrics_formatter)
    perf_logger.addHandler(perf_handler)
    
    # Setup error logger
    error_logger = logging.getLogger("errors")
    error_logger.setLevel(logging.ERROR)
    error_logger.handlers.clear()
    error_logger.propagate = False
    
    error_handler = logging.handlers.RotatingFileHandler(
        "logs/errors.log",
        maxBytes=20*1024*1024,  # 20MB
        backupCount=5
    )
    error_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    error_logger.addHandler(error_handler)

def get_metrics_logger():
    """Get the metrics logger instance"""
    return logging.getLogger("metrics")

def get_performance_logger():
    """Get the performance logger instance"""
    return logging.getLogger("performance")

def get_error_logger():
    """Get the error logger instance"""
    return logging.getLogger("errors")
