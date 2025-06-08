"""
Metrics and monitoring system for DhinSpeak System
path: core/metrics.py
"""

import asyncio
import time
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from collections import defaultdict, deque
import logging
from datetime import datetime, timedelta

from core.logging_config import get_metrics_logger, get_performance_logger

@dataclass
class TranslationMetrics:
    """Metrics for a single translation operation"""
    text_length: int
    source_lang: str
    target_lang: str
    preprocessing_time_ms: float
    translation_time_ms: float
    total_time_ms: float
    cache_hit: bool
    timestamp: datetime = field(default_factory=datetime.now)

@dataclass
class SystemMetrics:
    """System-wide metrics"""
    active_connections: int = 0
    total_translations: int = 0
    cache_hit_rate: float = 0.0
    avg_translation_time_ms: float = 0.0
    error_rate: float = 0.0
    uptime_seconds: float = 0.0

class MetricsManager:
    """Comprehensive metrics collection and analysis"""
    
    def __init__(self):
        self.metrics_logger = get_metrics_logger()
        self.perf_logger = get_performance_logger()
        
        # Metrics storage
        self.translation_metrics: deque = deque(maxlen=10000)  # Keep last 10k translations
        self.error_counts: Dict[str, int] = defaultdict(int)
        self.performance_data: Dict[str, deque] = {
            'translation_times': deque(maxlen=1000),
            'preprocessing_times': deque(maxlen=1000),
            'cache_hits': deque(maxlen=1000)
        }
        
        # System state
        self.start_time = time.time()
        self.total_requests = 0
        self.total_errors = 0
        
        # Rate limiting tracking
        self.client_requests: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        
    async def initialize(self):
        """Initialize metrics manager"""
        self.metrics_logger.info("SYSTEM_START | Metrics manager initialized")
        
    async def cleanup(self):
        """Cleanup metrics manager"""
        self.metrics_logger.info("SYSTEM_STOP | Metrics manager shutting down")
        await self._log_final_summary()
        
    def record_translation(self, metrics: TranslationMetrics, original_text: str, translated_text: str):
        """Record translation metrics"""
        self.translation_metrics.append(metrics)
        self.performance_data['translation_times'].append(metrics.translation_time_ms)
        self.performance_data['preprocessing_times'].append(metrics.preprocessing_time_ms)
        self.performance_data['cache_hits'].append(metrics.cache_hit)
        
        # Log detailed metrics for research
        self.metrics_logger.info(
            f"TRANSLATION | {metrics.source_lang}->{metrics.target_lang} | "
            f"Length: {metrics.text_length} | "
            f"Preproc: {metrics.preprocessing_time_ms:.2f}ms | "
            f"MT: {metrics.translation_time_ms:.2f}ms | "
            f"Total: {metrics.total_time_ms:.2f}ms | "
            f"Cache: {'HIT' if metrics.cache_hit else 'MISS'} | "
            f"Original: \"{original_text[:50]}{'...' if len(original_text) > 50 else ''}\" | "
            f"Translated: \"{translated_text[:50]}{'...' if len(translated_text) > 50 else ''}\""
        )
        
        self.total_requests += 1
        
    def record_error(self, error_type: str, error_message: str, context: Dict[str, Any] = None):
        """Record error occurrence"""
        self.error_counts[error_type] += 1
        self.total_errors += 1
        
        context_str = f" | Context: {context}" if context else ""
        self.metrics_logger.error(
            f"ERROR | Type: {error_type} | Message: {error_message}{context_str}"
        )
        
    def record_performance(self, operation: str, duration_ms: float, details: Dict[str, Any] = None):
        """Record performance metrics"""
        details_str = f" | {details}" if details else ""
        self.perf_logger.info(
            f"PERFORMANCE | {operation} | Duration: {duration_ms:.2f}ms{details_str}"
        )
        
    def check_rate_limit(self, client_id: str) -> bool:
        """Check if client is within rate limits"""
        now = time.time()
        client_queue = self.client_requests[client_id]
        
        # Remove old requests (older than 1 minute)
        while client_queue and now - client_queue[0] > 60:
            client_queue.popleft()
            
        # Check if under limit
        from core.config import settings
        if len(client_queue) >= settings.RATE_LIMIT_PER_MINUTE:
            return False
            
        # Add current request
        client_queue.append(now)
        return True
        
    async def get_health_metrics(self) -> Dict[str, Any]:
        """Get current health metrics"""
        now = time.time()
        uptime = now - self.start_time
        
        # Calculate averages
        recent_translations = list(self.performance_data['translation_times'])[-100:]  # Last 100
        avg_translation_time = sum(recent_translations) / len(recent_translations) if recent_translations else 0
        
        recent_cache_hits = list(self.performance_data['cache_hits'])[-100:]
        cache_hit_rate = sum(recent_cache_hits) / len(recent_cache_hits) if recent_cache_hits else 0
        
        error_rate = (self.total_errors / self.total_requests) if self.total_requests > 0 else 0
        
        return {
            "uptime_seconds": uptime,
            "total_requests": self.total_requests,
            "total_errors": self.total_errors,
            "error_rate": error_rate,
            "avg_translation_time_ms": avg_translation_time,
            "cache_hit_rate": cache_hit_rate,
            "active_clients": len(self.client_requests),
            "memory_usage_mb": self._get_memory_usage()
        }
        
    def get_detailed_stats(self) -> Dict[str, Any]:
        """Get detailed statistics for analysis"""
        translation_times = list(self.performance_data['translation_times'])
        preprocessing_times = list(self.performance_data['preprocessing_times'])
        
        def calculate_percentiles(data):
            if not data:
                return {"p50": 0, "p90": 0, "p95": 0, "p99": 0}
            sorted_data = sorted(data)
            n = len(sorted_data)
            return {
                "p50": sorted_data[int(n * 0.5)],
                "p90": sorted_data[int(n * 0.9)],
                "p95": sorted_data[int(n * 0.95)],
                "p99": sorted_data[int(n * 0.99)]
            }
        
        return {
            "translation_time_percentiles": calculate_percentiles(translation_times),
            "preprocessing_time_percentiles": calculate_percentiles(preprocessing_times),
            "error_breakdown": dict(self.error_counts),
            "language_pair_stats": self._get_language_pair_stats(),
            "hourly_request_distribution": self._get_hourly_distribution()
        }
        
    def _get_language_pair_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics by language pair"""
        stats = defaultdict(lambda: {"count": 0, "avg_time": 0, "total_time": 0})
        
        for metric in self.translation_metrics:
            pair = f"{metric.source_lang}->{metric.target_lang}"
            stats[pair]["count"] += 1
            stats[pair]["total_time"] += metric.translation_time_ms
            
        # Calculate averages
        for pair_stats in stats.values():
            if pair_stats["count"] > 0:
                pair_stats["avg_time"] = pair_stats["total_time"] / pair_stats["count"]
                
        return dict(stats)
        
    def _get_hourly_distribution(self) -> Dict[int, int]:
        """Get request distribution by hour"""
        hourly_counts = defaultdict(int)
        
        for metric in self.translation_metrics:
            hour = metric.timestamp.hour
            hourly_counts[hour] += 1
            
        return dict(hourly_counts)
        
    def _get_memory_usage(self) -> float:
        """Get current memory usage in MB"""
        try:
            import psutil
            process = psutil.Process()
            return process.memory_info().rss / 1024 / 1024  # Convert to MB
        except ImportError:
            return 0.0
            
    async def _log_final_summary(self):
        """Log final summary statistics"""
        health_metrics = await self.get_health_metrics()
        detailed_stats = self.get_detailed_stats()
        
        self.metrics_logger.info(
            f"FINAL_SUMMARY | "
            f"Uptime: {health_metrics['uptime_seconds']:.0f}s | "
            f"Total Requests: {health_metrics['total_requests']} | "
            f"Error Rate: {health_metrics['error_rate']:.3f} | "
            f"Avg Translation Time: {health_metrics['avg_translation_time_ms']:.2f}ms | "
            f"Cache Hit Rate: {health_metrics['cache_hit_rate']:.3f}"
        )
