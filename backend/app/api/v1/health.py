from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import time
import psutil
import os
from datetime import datetime

from app.db.database import get_db
from app.core.observability import vcos_metrics, http_requests_total, http_request_duration

router = APIRouter()


@router.get("/health")
async def health_check():
    return {"status": "healthy", "service": "vcos-api", "timestamp": datetime.utcnow().isoformat()}


@router.get("/health/db")
async def db_health_check(db: AsyncSession = Depends(get_db)):
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "healthy", "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "database": "disconnected", "error": str(e)}


@router.get("/health/live")
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_check(db: AsyncSession = Depends(get_db)):
    """Kubernetes readiness probe."""
    checks = {
        "database": "unknown",
        "redis": "unknown",
        "service": "unknown",
    }
    
    # Check database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception:
        checks["database"] = "unhealthy"
    
    # Check Redis (if configured)
    try:
        from app.core.presence_redis import get_redis_presence_service
        redis_service = await get_redis_presence_service()
        if redis_service._redis:
            await redis_service._redis.ping()
            checks["redis"] = "healthy"
        else:
            checks["redis"] = "not_configured"
    except Exception:
        checks["redis"] = "unhealthy"
    
    # Service health
    checks["service"] = "healthy"
    
    all_healthy = all(v == "healthy" or v == "not_configured" for v in checks.values())
    
    return {
        "status": "ready" if all_healthy else "not_ready",
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/metrics")
async def metrics_endpoint():
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/health/system")
async def system_health():
    """System resource health."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_percent": cpu_percent,
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": memory.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_percent": round((disk.used / disk.total) * 100, 1),
            },
            "process": {
                "pid": os.getpid(),
                "memory_mb": round(psutil.Process(os.getpid()).memory_info().rss / (1024**2), 1),
                "cpu_percent": psutil.Process(os.getpid()).cpu_percent(),
                "threads": psutil.Process(os.getpid()).num_threads(),
            },
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/health/dependencies")
async def dependencies_health():
    """Check external dependencies."""
    checks = {}
    
    # Database
    try:
        db = next(get_db())
        await db.execute(text("SELECT 1"))
        await db.close()
        checks["postgresql"] = {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        checks["postgresql"] = {"status": "unhealthy", "error": str(e)}
    
    # Redis
    try:
        from app.core.presence_redis import get_redis_presence_service
        redis_service = await get_redis_presence_service()
        start = time.time()
        if redis_service._redis:
            await redis_service._redis.ping()
        checks["redis"] = {"status": "healthy", "latency_ms": round((time.time() - start) * 1000, 2)}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
    
    return {"checks": checks, "timestamp": datetime.utcnow().isoformat()}