import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Application identity and environment
    APP_NAME: str = "TaskForge AI"
    APP_ENV: str = "development"  # 'development', 'staging', 'production'
    APP_DEBUG: bool = True
    LOG_LEVEL: str = "INFO"
    JSON_LOGS: bool = False

    # Security & Tokens
    SECRET_KEY: str = "taskforge-insecure-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # LLM API configuration
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Database configuration
    DATABASE_URL: str = "sqlite:///./taskforge.db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    DB_POOL_PRE_PING: bool = True

    # Frontend & CORS
    FRONTEND_URL: str = "http://localhost:5173"
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
    CORS_ORIGIN_REGEX: str = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$"

    # Artifacts & Uploads
    ARTIFACTS_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "artifacts")
    MAX_UPLOAD_SIZE_MB: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def is_production(self) -> bool:
        return self.APP_ENV.lower() in {"production", "prod"}

    @property
    def is_groq_configured(self) -> bool:
        return bool(self.GROQ_API_KEY and self.GROQ_API_KEY.strip() and not self.GROQ_API_KEY.startswith("your_"))

    @property
    def parsed_allowed_origins(self) -> List[str]:
        origins = [self.FRONTEND_URL]
        if self.ALLOWED_ORIGINS:
            for o in self.ALLOWED_ORIGINS.split(","):
                o_clean = o.strip()
                if o_clean and o_clean not in origins:
                    origins.append(o_clean)
        return origins


settings = Settings()
