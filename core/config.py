"""
Configuration management for DhinSpeak System
path: core/config.py
"""

import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    """Application settings"""
    
    # Server settings
    HOST: str = Field(default="0.0.0.0", description="Server host")
    PORT: int = Field(default=8000, description="Server port")
    DEBUG: bool = Field(default=False, description="Debug mode")
    
    # CORS settings
    ALLOWED_ORIGINS: List[str] = Field(default=["*"], description="Allowed CORS origins")
    
    # Firebase settings
    FIREBASE_CREDENTIALS_PATH: str = Field(default="firebase_credentials.json", description="Firebase credentials file path")
    FIREBASE_DATABASE_URL: str = Field(default="https://smarttranslation-aacf9-default-rtdb.asia-southeast1.firebasedatabase.app/", description="Firebase database URL")
    
    # Translation settings
    TRANSLATION_CACHE_SIZE: int = Field(default=1000, description="Translation cache size")
    MAX_TEXT_LENGTH: int = Field(default=500, description="Maximum text length for translation")
    TRANSLATION_TIMEOUT: float = Field(default=5.0, description="Translation timeout in seconds")
    
    # Model settings
    ID_EN_MODEL_NAME: str = Field(default="dhintech/marian-tedtalks-id-en", description="Indonesian to English model")
    EN_ID_MODEL_NAME: str = Field(default="Helsinki-NLP/opus-mt-en-id", description="English to Indonesian model")
    
    # Dictionary settings
    DICTIONARY_ID_PATH: str = Field(default="dictionary_id.txt", description="Indonesian dictionary path")
    DICTIONARY_EN_PATH: str = Field(default="dictionary_en.txt", description="English dictionary path")
    
    # Performance settings
    MAX_EDIT_DISTANCE: int = Field(default=2, description="Maximum edit distance for spell correction")
    PREFIX_LENGTH: int = Field(default=7, description="Prefix length for spell correction")
    MIN_WORD_FREQUENCY: int = Field(default=100, description="Minimum word frequency for spell correction")
    
    # WebSocket settings
    WS_HEARTBEAT_INTERVAL: int = Field(default=30, description="WebSocket heartbeat interval in seconds")
    MAX_CONNECTIONS_PER_ROOM: int = Field(default=50, description="Maximum connections per room")
    
    # Logging settings
    LOG_LEVEL: str = Field(default="INFO", description="Logging level")
    LOG_FORMAT: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", description="Log format")
    METRICS_LOG_FILE: str = Field(default="logs/nlp_metrics.log", description="Metrics log file path")
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = Field(default=100, description="Rate limit per minute per client")
    
    class Config:
        env_file = ".env"
        case_sensitive = True

# Global settings instance
settings = Settings()
