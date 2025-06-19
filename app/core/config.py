import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    SECRET_KEY: str
    SESSION_SECRET_KEY: str
    ADMIN_RELOAD_TOKEN: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str

    class Config:
        env_file = ".env"
        if not os.path.exists(".env") and os.path.exists("../.env"):
            env_file = "../.env"


settings = Settings()
