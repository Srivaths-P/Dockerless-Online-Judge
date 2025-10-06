from typing import List, Optional
from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    SECRET_KEY: str
    SESSION_SECRET_KEY: str
    ADMIN_RELOAD_TOKEN: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str
    GOOGLE_CLIENT_ID: Optional[str] = None
    GOOGLE_CLIENT_SECRET: Optional[str] = None
    ALLOWED_EMAIL_DOMAINS: List[str] = Field(default_factory=list)

    IDE_TIME_LIMIT_SEC: int = 1
    IDE_MEMORY_LIMIT_MB: int = 64
    IDE_RUN_COOLDOWN_SEC: int = 3
    DEFAULT_SUBMISSION_COOLDOWN_SEC: int = 10
    DEFAULT_GENERATOR_COOLDOWN_SEC: int = 10

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
