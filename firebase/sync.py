"""
Firebase synchronization for DhinSpeak System
path: firebase/sync.py
"""

import asyncio
import logging
import datetime
from typing import Dict, Any, Optional
import firebase_admin
from firebase_admin import credentials, db

from core.config import settings
from core.logging_config import get_error_logger

logger = logging.getLogger(__name__)
error_logger = get_error_logger()

class FirebaseManager:
    """Manages Firebase operations with error handling and retry logic"""
    
    def __init__(self):
        self._initialized = False
        self._db_ref = None
        
    async def initialize(self):
        """Initialize Firebase connection"""
        try:
            if not self._initialized:
                # Initialize Firebase Admin SDK
                cred = credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH)
                firebase_admin.initialize_app(cred, {
                    'databaseURL': settings.FIREBASE_DATABASE_URL
                })
                
                self._db_ref = db.reference('/')
                self._initialized = True
                logger.info("Firebase initialized successfully")
            
        except Exception as e:
            error_logger.error(f"Failed to initialize Firebase: {e}")
            raise
            
    async def cleanup(self):
        """Cleanup Firebase connections"""
        try:
            if self._initialized:
                # Firebase Admin SDK doesn't need explicit cleanup
                self._initialized = False
                logger.info("Firebase cleanup completed")
        except Exception as e:
            error_logger.error(f"Error during Firebase cleanup: {e}")
            
    def is_initialized(self) -> bool:
        """Check if Firebase is initialized"""
        return self._initialized
        
    async def save_translation(self, room_code: str, original_text: str, translated_text: str, 
                             source_lang: str, target_lang: str, 
                             metrics: Optional[Dict[str, Any]] = None) -> bool:
        """
        Save translation to Firebase with comprehensive error handling
        Returns: True if successful, False otherwise
        """
        if not self._initialized:
            logger.warning("Firebase not initialized, skipping save")
            return False
            
        # Validate input to prevent saving control messages
        if self._is_control_message(original_text) or self._is_control_message(translated_text):
            logger.warning(f"Blocked control message from Firebase: {original_text[:50]}")
            return False
            
        try:
            # Create message data
            message_data = {
                'original': original_text,
                'translated': translated_text,
                'lang_source': source_lang,
                'lang_target': target_lang,
                'timestamp': datetime.datetime.now().isoformat(),
                'metrics': metrics or {}
            }
            
            # Save to Firebase with retry logic
            success = await self._save_with_retry(f'/messages/{room_code}', message_data)
            
            if success:
                logger.debug(f"Saved translation to Firebase for room {room_code}")
            else:
                logger.error(f"Failed to save translation to Firebase for room {room_code}")
                
            return success
            
        except Exception as e:
            error_logger.error(f"Error saving translation to Firebase: {e}")
            return False
            
    async def create_room(self, room_code: str, language: str) -> bool:
        """Create a new room in Firebase"""
        if not self._initialized:
            logger.warning("Firebase not initialized, skipping room creation")
            return False
            
        try:
            initial_message = {
                'original': " ",
                'translated': " ",
                'lang_source': language,
                'lang_target': 'en' if language == 'id' else 'id',
                'timestamp': datetime.datetime.now().isoformat(),
                'room_created': True
            }
            
            success = await self._save_with_retry(f'/messages/{room_code}', initial_message)
            
            if success:
                logger.info(f"Created room {room_code} in Firebase")
            else:
                logger.error(f"Failed to create room {room_code} in Firebase")
                
            return success
            
        except Exception as e:
            error_logger.error(f"Error creating room in Firebase: {e}")
            return False
            
    async def delete_room(self, room_code: str) -> bool:
        """Delete room data from Firebase"""
        if not self._initialized:
            logger.warning("Firebase not initialized, skipping room deletion")
            return False
            
        try:
            success = await self._delete_with_retry(f'/messages/{room_code}')
            
            if success:
                logger.info(f"Deleted room {room_code} from Firebase")
            else:
                logger.error(f"Failed to delete room {room_code} from Firebase")
                
            return success
            
        except Exception as e:
            error_logger.error(f"Error deleting room from Firebase: {e}")
            return False
            
    async def get_room_data(self, room_code: str) -> Optional[Dict[str, Any]]:
        """Get room data from Firebase"""
        if not self._initialized:
            logger.warning("Firebase not initialized, cannot get room data")
            return None
            
        try:
            ref = db.reference(f'/messages/{room_code}')
            data = await asyncio.get_event_loop().run_in_executor(None, ref.get)
            return data
            
        except Exception as e:
            error_logger.error(f"Error getting room data from Firebase: {e}")
            return None
            
    def _is_control_message(self, text: str) -> bool:
        """Check if text is a control message that shouldn't be saved"""
        if not text:
            return False
            
        control_indicators = [
            "CONTROL:",
            "{\"type\"",
            "\"type\":",
            "language",
            "control",
            "fontcolor",
            "ping",
            "pong",
            "partial_speech",
            "close_room"
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in control_indicators)
        
    async def _save_with_retry(self, path: str, data: Dict[str, Any], max_retries: int = 3) -> bool:
        """Save data to Firebase with retry logic"""
        for attempt in range(max_retries):
            try:
                ref = db.reference(path)
                await asyncio.get_event_loop().run_in_executor(None, ref.set, data)
                return True
                
            except Exception as e:
                logger.warning(f"Firebase save attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                else:
                    error_logger.error(f"All Firebase save attempts failed for path {path}")
                    
        return False
        
    async def _delete_with_retry(self, path: str, max_retries: int = 3) -> bool:
        """Delete data from Firebase with retry logic"""
        for attempt in range(max_retries):
            try:
                ref = db.reference(path)
                await asyncio.get_event_loop().run_in_executor(None, ref.delete)
                return True
                
            except Exception as e:
                logger.warning(f"Firebase delete attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff
                else:
                    error_logger.error(f"All Firebase delete attempts failed for path {path}")
                    
        return False
        
    async def get_health_status(self) -> Dict[str, Any]:
        """Get Firebase health status"""
        if not self._initialized:
            return {
                "status": "not_initialized",
                "connected": False,
                "error": "Firebase not initialized"
            }
            
        try:
            # Test connection by reading a small piece of data
            ref = db.reference('/.info/connected')
            connected = await asyncio.get_event_loop().run_in_executor(None, ref.get)
            
            return {
                "status": "healthy" if connected else "disconnected",
                "connected": bool(connected),
                "initialized": self._initialized
            }
            
        except Exception as e:
            return {
                "status": "error",
                "connected": False,
                "error": str(e)
            }
