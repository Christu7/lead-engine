from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://leadengine:leadengine@db:5432/leadengine"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "change-me-in-production"
    CORS_ORIGINS: str = "http://localhost:3000"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    BACKEND_URL: str = "http://localhost:8000"
    FRONTEND_URL: str = "http://localhost:3000"
    APOLLO_WEBHOOK_SECRET: str = ""
    APOLLO_API_KEY: str = ""
    ADMIN_EMAIL: str = "admin@leadengine.local"
    ADMIN_PASSWORD: str = "changeme"
    DEFAULT_CLIENT_NAME: str = "Default"
    LOG_LEVEL: str = "INFO"
    SENTRY_DSN: str = ""
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    CLEARBIT_API_KEY: str = ""
    PROXYCURL_API_KEY: str = ""
    ENCRYPTION_KEY: str = ""
    AI_PROVIDER: str = "anthropic"
    DEBUG: bool = False
    TEST_DATABASE_URL: str = ""

    model_config = {"env_file": ".env"}


settings = Settings()
