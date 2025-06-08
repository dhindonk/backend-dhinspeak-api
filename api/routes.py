
"""
API routes for DhinSpeak System
path: api/routes.py
"""

import logging
import random
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.config import settings

logger = logging.getLogger(__name__)

# Pydantic models for request/response
class CreateRoomRequest(BaseModel):
    language: str = "id"

class CreateRoomResponse(BaseModel):
    status: str
    room_code: str
    language: str

class HealthResponse(BaseModel):
    status: str
    models_loaded: bool
    firebase_connected: bool
    metrics: Dict[str, Any]

# Create router
api_router = APIRouter()

def generate_room_code() -> str:
    """Generate a unique 4-character room code"""
    letters = 'ABCDEFGHJKLMNPQRSTUVWXYZ'  # Removed confusing chars like I, O
    numbers = '23456789'  # Removed confusing numbers like 0, 1
    
    return ''.join([
        random.choice(letters),
        random.choice(numbers),
        random.choice(letters),
        random.choice(numbers)
    ])

@api_router.post("/create-room", response_model=CreateRoomResponse)
async def create_room(request: CreateRoomRequest):
    """Create a new translation room"""
    try:
        # Import here to avoid circular imports
        from main import model_manager, metrics_manager, firebase_manager
        from ws_router import manager as ws_manager
        
        # Generate unique room code
        room_code = generate_room_code()
        existing_rooms = list(ws_manager.active_connections.keys())
        
        # Ensure uniqueness
        while room_code in existing_rooms:
            room_code = generate_room_code()
        
        # Validate language
        if request.language not in ['id', 'en']:
            raise HTTPException(status_code=400, detail="Invalid language. Must be 'id' or 'en'")
        
        # Set room language in WebSocket manager
        ws_manager.set_room_language(room_code, request.language)
        
        # Create room in Firebase
        if firebase_manager and firebase_manager.is_initialized():
            await firebase_manager.create_room(room_code, request.language)
        
        logger.info(f"Created room {room_code} with language {request.language}")
        
        return CreateRoomResponse(
            status="success",
            room_code=room_code,
            language=request.language
        )
        
    except Exception as e:
        logger.error(f"Error creating room: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create room: {str(e)}")

@api_router.get("/rooms")
async def get_active_rooms():
    """Get list of active rooms"""
    try:
        from ws_router import manager as ws_manager
        
        rooms = []
        for room_code in ws_manager.active_connections.keys():
            rooms.append({
                "room_code": room_code,
                "language": ws_manager.get_room_language(room_code),
                "active_connections": len(ws_manager.active_connections[room_code])
            })
        
        return {"active_rooms": rooms, "total_rooms": len(rooms)}
        
    except Exception as e:
        logger.error(f"Error getting active rooms: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get rooms: {str(e)}")

@api_router.post("/set-language/{room_code}")
async def set_room_language(room_code: str, language: str):
    """Set language for a specific room"""
    try:
        from ws_router import manager as ws_manager
        
        if language not in ['id', 'en']:
            raise HTTPException(status_code=400, detail="Invalid language. Must be 'id' or 'en'")
        
        if room_code not in ws_manager.active_connections:
            raise HTTPException(status_code=404, detail="Room not found")
        
        ws_manager.set_room_language(room_code, language)
        
        return {
            "status": "success",
            "room_code": room_code,
            "language": language
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error setting room language: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to set language: {str(e)}")

@api_router.get("/health", response_model=HealthResponse)
async def detailed_health_check():
    """Comprehensive health check endpoint"""
    try:
        from main import model_manager, metrics_manager
        from firebase.sync import FirebaseManager
        
        # Check model status
        models_loaded = model_manager.is_ready() if model_manager else False
        
        # Check Firebase status
        firebase_manager = FirebaseManager()
        firebase_status = await firebase_manager.get_health_status()
        firebase_connected = firebase_status.get("connected", False)
        
        # Get metrics
        health_metrics = await metrics_manager.get_health_metrics() if metrics_manager else {}
        
        # Overall status
        overall_status = "healthy" if (models_loaded and firebase_connected) else "degraded"
        
        return HealthResponse(
            status=overall_status,
            models_loaded=models_loaded,
            firebase_connected=firebase_connected,
            metrics=health_metrics
        )
        
    except Exception as e:
        logger.error(f"Error in health check: {e}")
        return HealthResponse(
            status="error",
            models_loaded=False,
            firebase_connected=False,
            metrics={"error": str(e)}
        )

@api_router.get("/metrics")
async def get_detailed_metrics():
    """Get detailed system metrics for monitoring"""
    try:
        from main import model_manager, metrics_manager
        from ws_router import manager as ws_manager
        
        # Basic system info
        system_info = {
            "models_ready": model_manager.is_ready() if model_manager else False,
            "model_info": model_manager.get_model_info() if model_manager else {},
            "active_rooms": len(ws_manager.active_connections),
            "total_connections": sum(len(conns) for conns in ws_manager.active_connections.values())
        }
        
        # Detailed metrics
        if metrics_manager:
            health_metrics = await metrics_manager.get_health_metrics()
            detailed_stats = metrics_manager.get_detailed_stats()
            
            return {
                "system": system_info,
                "health": health_metrics,
                "detailed": detailed_stats,
                "timestamp": health_metrics.get("uptime_seconds", 0)
            }
        else:
            return {
                "system": system_info,
                "health": {},
                "detailed": {},
                "timestamp": 0
            }
            
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")

@api_router.get("/cache-stats")
async def get_cache_stats():
    """Get translation cache statistics"""
    try:
        from main import model_manager
        from translation.translator import TranslationEngine
        
        # This would need to be implemented properly with dependency injection
        # For now, return basic info
        return {
            "message": "Cache stats endpoint - implementation depends on proper DI setup",
            "models_loaded": model_manager.is_ready() if model_manager else False
        }
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cache stats: {str(e)}")

@api_router.post("/clear-cache")
async def clear_translation_cache():
    """Clear translation cache (admin endpoint)"""
    try:
        # This would need proper authentication in production
        logger.info("Cache clear requested via API")
        
        return {
            "status": "success",
            "message": "Cache clear endpoint - implementation depends on proper DI setup"
        }
        
    except Exception as e:
        logger.error(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to clear cache: {str(e)}")

@api_router.get("/room/{room_code}/data")
async def get_room_data(room_code: str):
    """Get room data from Firebase"""
    try:
        from firebase.sync import FirebaseManager
        
        firebase_manager = FirebaseManager()
        if not firebase_manager.is_initialized():
            raise HTTPException(status_code=503, detail="Firebase not available")
        
        room_data = await firebase_manager.get_room_data(room_code)
        
        if room_data is None:
            raise HTTPException(status_code=404, detail="Room not found")
        
        return {
            "room_code": room_code,
            "data": room_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting room data: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get room data: {str(e)}")

@api_router.delete("/room/{room_code}")
async def delete_room(room_code: str):
    """Delete room and its data"""
    try:
        from firebase.sync import FirebaseManager
        from ws_router import manager as ws_manager
        
        # Remove from WebSocket manager
        if room_code in ws_manager.active_connections:
            # Close all connections in the room
            connections = list(ws_manager.active_connections[room_code])
            for conn in connections:
                try:
                    await conn.close()
                except:
                    pass
            
            # Remove room
            del ws_manager.active_connections[room_code]
            if room_code in ws_manager.room_languages:
                del ws_manager.room_languages[room_code]
        
        # Delete from Firebase
        firebase_manager = FirebaseManager()
        if firebase_manager.is_initialized():
            await firebase_manager.delete_room(room_code)
        
        logger.info(f"Deleted room {room_code}")
        
        return {
            "status": "success",
            "message": f"Room {room_code} deleted successfully"
        }
        
    except Exception as e:
        logger.error(f"Error deleting room: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete room: {str(e)}")
