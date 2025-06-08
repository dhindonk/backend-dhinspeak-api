"""
DhinSpeak System - Main Entry Point
Professional real-time translation backend with WebSocket support
path: main.py
"""

import uvicorn
import logging
import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.config import settings
from core.logging_config import setup_logging
from ws_router import websocket_router, initialize_components, metrics_pusher
from api.routes import api_router
from translation.model_loader import ModelManager
from core.metrics import MetricsManager
from firebase.sync import FirebaseManager

# Setup logging
setup_logging()
logger = logging.getLogger(__name__)

# Global instances
model_manager = ModelManager()
metrics_manager = MetricsManager()
firebase_manager = FirebaseManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info(" Starting DhinSpeak System...")
    
    # Initialize models and services
    await model_manager.initialize()
    await metrics_manager.initialize()
    await firebase_manager.initialize()
    
    # Initialize WebSocket components
    initialize_components(model_manager, metrics_manager, firebase_manager)
    
    # Start background tasks
    metrics_task = asyncio.create_task(metrics_pusher())
    
    logger.info("System initialization completed")
    
    yield
    
    # Cleanup
    logger.info("Shutting down system...")
    metrics_task.cancel()
    await model_manager.cleanup()
    await metrics_manager.cleanup()
    await firebase_manager.cleanup()
    logger.info("System shutdown completed")

# Create FastAPI app with lifespan
app = FastAPI(
    title="DhinSpeak API",
    description="Professional real-time translation system with WebSocket support",
    version="2.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(websocket_router, prefix="/ws")
app.include_router(api_router, prefix="/api")

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "DhinSpeak API v2.0 is running",
        "status": "healthy",
        "version": "2.0.0"
    }

@app.get("/health")
async def health_check():
    """Detailed health check"""
    from ws_router import manager
    
    return {
        "status": "healthy",
        "models_loaded": model_manager.is_ready(),
        "firebase_connected": firebase_manager.is_initialized(),
        "active_connections": len(manager.active_connections),
        "metrics": await metrics_manager.get_health_metrics()
    }

if __name__ == "__main__":
    logger.info("Starting server in production mode...")
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=False,
        workers=1,
        log_level="info",
        access_log=True,
        proxy_headers=True,
        forwarded_allow_ips="*",
        ws_ping_interval=20,  # Enable WebSocket ping
        ws_ping_timeout=30,   # WebSocket timeout
        timeout_keep_alive=65  # Keep-alive timeout
    )
