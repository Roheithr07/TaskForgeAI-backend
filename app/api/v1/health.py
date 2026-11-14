import os
import time
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database.session import get_db
from app.core.config import settings

router = APIRouter()

START_TIME = time.time()


@router.get("/health")
def health_check():
    """
    Liveness probe: verifies that the FastAPI application process is alive and responding.
    Used by load balancers, orchestrators, and monitoring daemons.
    """
    uptime_seconds = int(time.time() - START_TIME)
    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "uptime_seconds": uptime_seconds,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/ready")
def readiness_check(response: Response, db: Session = Depends(get_db)):
    """
    Readiness probe: verifies that all backing dependencies (database, artifacts storage)
    are reachable, operational, and writable before routing traffic to this instance.
    Returns HTTP 200 if ready, or HTTP 503 if any critical service is degraded.
    """
    checks = {
        "database": False,
        "artifacts_storage": False,
        "groq_configured": settings.is_groq_configured
    }

    # 1. Database read/ping check
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception as e:
        checks["database_error"] = str(e)

    # 2. Storage write/read check
    try:
        os.makedirs(settings.ARTIFACTS_DIR, exist_ok=True)
        probe_file = os.path.join(settings.ARTIFACTS_DIR, ".ready_probe")
        with open(probe_file, "w") as f:
            f.write("ok")
        if os.path.exists(probe_file):
            os.remove(probe_file)
            checks["artifacts_storage"] = True
    except Exception as e:
        checks["storage_error"] = str(e)

    is_ready = checks["database"] and checks["artifacts_storage"]
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": "ready" if is_ready else "not_ready",
        "app_name": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
