import os
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    APP_NAME: str = "HackRND Finance AI Service"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    
    # Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgrespassword@localhost:5432/hackrnd_db")
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://:HackRndRedis2026!@localhost:6379/0")
    
    # Session & Auth
    SESSION_SECRET: str = os.getenv("SESSION_SECRET", "hackrnd-dev-secret-change-in-production")
    SESSION_MAX_AGE_SECONDS: int = 86400 * 7  # 7 days
    COOKIE_NAME: str = "session_id"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    
    # LLM Configuration (Gemini Pool)
    GEMINI_API_KEYS: str = os.getenv("GEMINI_API_KEYS", "")
    GEMINI_TIMEOUT_SECONDS: float = 10.0
    
    TRUSTED_PROXIES: list[str] = ["127.0.0.1", "::1", "localhost", "testclient"]
    
    # CORS (Hardened: explicit origins only, wildcard disallowed with credentials)
    CORS_ORIGINS: list[str] | str = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://localhost",
        "http://127.0.0.1",
        "http://194.113.106.233:8000",
        "http://194.113.106.233",
    ]

    @field_validator("CORS_ORIGINS")
    @classmethod
    def assemble_cors_origins(cls, v: list[str] | str) -> list[str]:
        origins: list[str] = []
        if isinstance(v, str):
            if v.strip().startswith("["):
                import json
                try:
                    res = json.loads(v)
                    if isinstance(res, list):
                        origins = res
                except Exception:
                    pass
            if not origins:
                origins = [orig.strip() for orig in v.split(",") if orig.strip()]
        elif isinstance(v, list):
            origins = v
        else:
            origins = list(v)

        cleaned = [o.strip() for o in origins if o and o.strip() != "*"]
        if not cleaned:
            cleaned = [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:4173",
                "http://127.0.0.1:4173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
                "http://localhost:8000",
                "http://127.0.0.1:8000",
                "http://localhost",
                "http://127.0.0.1",
            ]
        return cleaned
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    @property
    def api_keys_list(self) -> list[str]:
        return [k.strip() for k in self.GEMINI_API_KEYS.split(",") if k.strip()]

settings = Settings()
