import uuid
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.database.session import init_db
from app.api.v1.router import api_v1_router

# Initialize structured or standard logging
setup_logging(
    level=settings.LOG_LEVEL,
    json_logs=settings.JSON_LOGS or settings.is_production
)

logger = logging.getLogger("taskforge.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    logger.info("Initializing TaskForge AI services (Environment: %s)", settings.APP_ENV)
    init_db()
    yield
    logger.info("Shutting down TaskForge AI services gracefully.")


# Ensure tables are initialized
init_db()

app = FastAPI(
    title=settings.APP_NAME,
    description="Autonomous AI Workflow Automation Platform with Human-in-the-Loop Orchestration",
    version="1.0.0",
    docs_url="/docs" if not settings.is_production or settings.APP_DEBUG else None,
    redoc_url="/redoc" if not settings.is_production or settings.APP_DEBUG else None,
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_allowed_origins,
    allow_origin_regex=settings.CORS_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler ensuring no internal stack traces or database errors
    are leaked to clients in production environments.
    """
    error_id = str(uuid.uuid4())
    logger.error("Unhandled exception [Error ID: %s] on %s %s: %s", error_id, request.method, request.url.path, exc, exc_info=True)

    if settings.is_production and not settings.APP_DEBUG:
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error. Please contact system administrator.",
                "error_id": error_id
            }
        )
    return JSONResponse(
        status_code=500,
        content={
            "detail": str(exc),
            "error_id": error_id
        }
    )


app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/")
def root():
    return {
        "service": settings.APP_NAME,
        "environment": settings.APP_ENV,
        "docs": "/docs" if not settings.is_production or settings.APP_DEBUG else "disabled_in_production",
        "health": "/api/v1/health",
        "ready": "/api/v1/ready"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.APP_DEBUG)
