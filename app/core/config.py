from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://leadengine:leadengine@db:5432/leadengine"
    REDIS_URL: str = "redis://redis:6379/0"
    SECRET_KEY: str = "change-me-in-production"

    model_config = {"env_file": ".env"}


settings = Settings()
