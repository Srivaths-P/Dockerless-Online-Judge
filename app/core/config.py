from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    SECRET_KEY: str
    SESSION_SECRET_KEY: str
    ADMIN_RELOAD_TOKEN: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding='utf-8',
        extra='ignore'  # You can add this to ignore extra env vars if needed
    )


settings = Settings()
