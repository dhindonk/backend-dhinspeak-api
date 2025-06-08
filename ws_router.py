"""
WebSocket router for DhinSpeak System
path: ws_router.py
"""

import asyncio
import json
import logging
import time
from typing import Dict, Set, Optional
from datetime import datetime
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from core.config import settings
from core.metrics import TranslationMetrics, MetricsManager
from core.logging_config import get_error_logger
from translation.model_loader import ModelManager
from translation.translator import TranslationEngine
from firebase.sync import FirebaseManager

logger = logging.getLogger(__name__)
error_logger = get_error_logger()

class ConnectionManager:
    """Enhanced WebSocket connection manager with rate limiting and monitoring"""
    
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.room_languages: Dict[str, str] = {}
        self.client_last_message: Dict[int, str] = {}
        self.metrics_connections: Set[WebSocket] = set()
        
    async def connect(self, websocket: WebSocket, room_code: str):
        """Connect client to room"""
        await websocket.accept()
        
        if room_code not in self.active_connections:
            self.active_connections[room_code] = set()
            
        # Check room capacity
        if len(self.active_connections[room_code]) >= settings.MAX_CONNECTIONS_PER_ROOM:
            await websocket.close(code=1008, reason="Room is full")
            return False
            
        self.active_connections[room_code].add(websocket)
        logger.info(f"Client connected to room {room_code} ({len(self.active_connections[room_code])} total)")
        return True

    def disconnect(self, websocket: WebSocket, room_code: str):
        """Disconnect client from room"""
        if room_code in self.active_connections:
            self.active_connections[room_code].discard(websocket)
            
            # Clean up empty rooms
            if not self.active_connections[room_code]:
                del self.active_connections[room_code]
                if room_code in self.room_languages:
                    del self.room_languages[room_code]
                    
        # Clean up client tracking
        client_id = id(websocket)
        if client_id in self.client_last_message:
            del self.client_last_message[client_id]
            
        logger.info(f"Client disconnected from room {room_code}")

    def set_room_language(self, room_code: str, language: str):
        """Set language for room"""
        self.room_languages[room_code] = language
        logger.info(f"Language for room {room_code} set to {language}")

    def get_room_language(self, room_code: str) -> str:
        """Get room language"""
        return self.room_languages.get(room_code, 'id')
        
    def is_duplicate_message(self, websocket: WebSocket, message: str) -> bool:
        """Check if message is duplicate from same client"""
        client_id = id(websocket)
        
        if client_id in self.client_last_message:
            if self.client_last_message[client_id] == message:
                return True
                
        self.client_last_message[client_id] = message
        return False
        
    async def broadcast_to_room(self, room_code: str, message: dict):
        """Broadcast message to all connections in room"""
        if room_code not in self.active_connections:
            return
            
        disconnected = []
        
        for connection in self.active_connections[room_code]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to client: {e}")
                disconnected.append(connection)
                
        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn, room_code)

    async def broadcast_metrics(self, metrics: dict):
        """Broadcast metrics to all connected metrics clients"""
        disconnected = []
        for connection in self.metrics_connections:
            try:
                await connection.send_json(metrics)
            except Exception as e:
                logger.warning(f"Failed to send metrics to client: {e}")
                disconnected.append(connection)
        
        for conn in disconnected:
            self.metrics_connections.discard(conn)

# Global connection manager
manager = ConnectionManager()

# Create WebSocket router
websocket_router = APIRouter()

# Global instances (will be injected from main.py)
model_manager: Optional[ModelManager] = None
metrics_manager: Optional[MetricsManager] = None
firebase_manager: Optional[FirebaseManager] = None
translation_engine: Optional[TranslationEngine] = None

def initialize_components(mm: ModelManager, met: MetricsManager, fm: FirebaseManager):
    """Initialize global components"""
    global model_manager, metrics_manager, firebase_manager, translation_engine
    
    model_manager = mm
    metrics_manager = met
    firebase_manager = fm
    
    # Initialize translation components
    translation_engine = TranslationEngine(model_manager)
    
    logger.info("WebSocket components initialized")

@websocket_router.websocket("/{room_code}")
async def websocket_endpoint(websocket: WebSocket, room_code: str):
    """Main WebSocket endpoint for real-time translation"""
    logger.info(f"WebSocket connection attempt to room {room_code}")
    try:
        # Connect to room
        connected = await manager.connect(websocket, room_code)
        if not connected:
            logger.error(f"Failed to connect to room {room_code}")
            return
        logger.info(f"Successfully connected to room {room_code}")
    except Exception as e:
        logger.error(f"Connection error: {e}")
        return
    
        
    client_id = id(websocket)
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            
            # Log received message
            logger.debug(f"📥 Received in room {room_code}: {data[:100]}")
            
            # Check for control messages
            if await handle_control_message(websocket, room_code, data):
                continue
                
            # Check for duplicate messages
            if manager.is_duplicate_message(websocket, data):
                logger.debug(f"🔄 Duplicate message detected, skipping: {data[:30]}")
                await send_acknowledgment(websocket, "Message received (duplicate ignored)")
                continue
                
            # Skip default placeholder messages
            if is_placeholder_message(data):
                logger.debug("⏭️ Skipping default placeholder message")
                await send_placeholder_response(websocket, data)
                continue
                
            # Rate limiting check
            if not check_rate_limit(client_id):
                logger.warning(f"⚠️ Rate limit exceeded for client {client_id}")
                await send_error(websocket, "Rate limit exceeded")
                continue
                
            # Process translation
            await process_translation_message(websocket, room_code, data)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket, room_code)
    except Exception as e:
        error_logger.error(f"❌ Unexpected error in websocket: {e}")
        manager.disconnect(websocket, room_code)

async def handle_control_message(websocket: WebSocket, room_code: str, data: str) -> bool:
    """Handle control messages (language setting, ping, etc.)"""
    try:
        # Check for JSON control messages
        if data.strip().startswith("{"):
            try:
                json_data = json.loads(data)
                if isinstance(json_data, dict) and "type" in json_data:
                    return await process_control_json(websocket, room_code, json_data)
            except json.JSONDecodeError:
                pass
                
        # Check for CONTROL: prefix
        if "CONTROL:" in data:
            try:
                control_part = data.split("CONTROL:")[1]
                control_data = json.loads(control_part)
                return await process_control_json(websocket, room_code, control_data)
            except (json.JSONDecodeError, IndexError):
                pass
                
    except Exception as e:
        error_logger.error(f"Error processing control message: {e}")
        
    return False

async def process_control_json(websocket: WebSocket, room_code: str, json_data: dict) -> bool:
    """Process JSON control messages"""
    message_type = json_data.get("type")
    
    if message_type == "language":
        language = json_data.get("language")
        if language:
            manager.set_room_language(room_code, language)
            await websocket.send_json({
                "status": "ok",
                "message": "Language set successfully"
            })
        return True
        
    elif message_type == "ping":
        await websocket.send_json({
            "type": "pong",
            "timestamp": json_data.get("timestamp"),
            "server_time": datetime.now().isoformat()
        })
        return True
        
    elif message_type == "partial_speech":
        await process_partial_speech(websocket, room_code, json_data)
        return True
        
    elif message_type == "close_room":
        await process_room_closure(websocket, room_code, json_data)
        return True
        
    return False

async def process_partial_speech(websocket: WebSocket, room_code: str, json_data: dict):
    """Process partial speech for real-time translation"""
    text = json_data.get("text", "")
    language = json_data.get("language", "id")
    
    if not text or not translation_engine:
        return
        
    target_lang = 'en' if language == 'id' else 'id'
    
    try:
        # Fast translation for partial results
        translated_text, metrics = await translation_engine.translate_text(
            text, language, target_lang, is_partial=True
        )
        
        # Broadcast partial translation
        response_data = {
            'type': 'partial_translation',
            'original': text,
            'translated': translated_text,
            'lang_source': language,
            'lang_target': target_lang,
            'is_partial': True,
            'processing_time_ms': round(metrics.total_time_ms, 2)
        }
        
        await manager.broadcast_to_room(room_code, response_data)
        
    except Exception as e:
        error_logger.error(f"Error processing partial speech: {e}")

async def process_room_closure(websocket: WebSocket, room_code: str, json_data: dict):
    """Process room closure request"""
    delete_data = json_data.get("delete_data", False)
    
    if delete_data and firebase_manager:
        try:
            await firebase_manager.delete_room(room_code)
            logger.info(f"Deleted data for room {room_code}")
        except Exception as e:
            error_logger.error(f"Error deleting room data: {e}")
    
    # Notify all clients
    closure_message = {
        "status": "room_closed",
        "message": "The room has been closed by the speaker"
    }
    
    await manager.broadcast_to_room(room_code, closure_message)
    
    # Acknowledge to requester
    await websocket.send_json({
        "status": "ok",
        "message": "Room closed successfully"
    })

def is_placeholder_message(data: str) -> bool:
    """Check if message is a placeholder"""
    placeholders = [
        "tekan tombol dan mulai berbicara",
        "Press the button and start speaking"
    ]
    return data.strip() in placeholders

async def send_placeholder_response(websocket: WebSocket, data: str):
    """Send response for placeholder messages"""
    if data.strip() == "tekan tombol dan mulai berbicara":
        translation = "Press the button and start speaking"
    else:
        translation = "Tekan tombol dan mulai berbicara"
        
    await websocket.send_json({
        "original": data,
        "translated": translation,
        "status": "default_message"
    })

def check_rate_limit(client_id: int) -> bool:
    """Check if client is within rate limits"""
    if not metrics_manager:
        return True
        
    return metrics_manager.check_rate_limit(str(client_id))

async def process_translation_message(websocket: WebSocket, room_code: str, data: str):
    """Process regular translation message"""
    if not translation_engine or not metrics_manager:
        await send_error(websocket, "Translation service not available")
        return
        
    try:
        # Get room language
        source_lang = manager.get_room_language(room_code)
        target_lang = 'en' if source_lang == 'id' else 'id'
        
        # Perform translation
        translated_text, metrics = await translation_engine.translate_text(
            data, source_lang, target_lang
        )
        
        # Record metrics
        metrics_manager.record_translation(metrics, data, translated_text)
        
        # Save to Firebase
        if firebase_manager:
            asyncio.create_task(
                firebase_manager.save_translation(
                    room_code, data, translated_text, source_lang, target_lang,
                    {
                        "processing_time_ms": metrics.total_time_ms,
                        "cache_hit": metrics.cache_hit
                    }
                )
            )
        
        # Broadcast result
        response_data = {
            'original': data,
            'translated': translated_text,
            'lang_source': source_lang,
            'lang_target': target_lang,
            'status': 'ok',
            'processing_time_ms': round(metrics.total_time_ms, 2),
            'cache_hit': metrics.cache_hit
        }
        
        await manager.broadcast_to_room(room_code, response_data)
        
    except Exception as e:
        error_logger.error(f"Error processing translation: {e}")
        if metrics_manager:
            metrics_manager.record_error("translation_error", str(e), {"room": room_code})
        await send_error(websocket, "Translation failed")

async def send_acknowledgment(websocket: WebSocket, message: str):
    """Send acknowledgment message"""
    try:
        await websocket.send_json({
            "status": "ok",
            "message": message
        })
    except Exception as e:
        logger.error(f"Error sending acknowledgment: {e}")

async def send_error(websocket: WebSocket, error_message: str):
    """Send error message"""
    try:
        await websocket.send_json({
            "status": "error",
            "message": error_message
        })
    except Exception as e:
        logger.error(f"Error sending error message: {e}")

@websocket_router.websocket("/metrics")
async def metrics_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time system metrics"""
    await websocket.accept()
    manager.metrics_connections.add(websocket)
    logger.info("Metrics client connected")
    
    try:
        while True:
            # This loop keeps the connection alive.
            # The actual metrics are sent by a background task.
            await asyncio.sleep(1)
            # We can also handle incoming messages if needed, e.g., to change update frequency
            # data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.metrics_connections.discard(websocket)
        logger.info("Metrics client disconnected")
    except Exception as e:
        manager.metrics_connections.discard(websocket)
        error_logger.error(f"Error in metrics websocket: {e}")

async def metrics_pusher():
    """Periodically push metrics to connected clients"""
    while True:
        await asyncio.sleep(5) # Push metrics every 5 seconds
        if manager.metrics_connections:
            try:
                if metrics_manager:
                    health_metrics = await metrics_manager.get_health_metrics()
                    detailed_stats = metrics_manager.get_detailed_stats()
                    
                    # Combine metrics into a single payload
                    payload = {
                        "type": "metrics_update",
                        "health": health_metrics,
                        "detailed": detailed_stats,
                        "timestamp": datetime.now().isoformat()
                    }
                    await manager.broadcast_metrics(payload)
            except Exception as e:
                error_logger.error(f"Error pushing metrics: {e}")

# Add the metrics pusher to the application lifespan
# This requires a modification in main.py to start this task
