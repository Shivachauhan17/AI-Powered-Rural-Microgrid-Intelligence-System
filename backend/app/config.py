from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "AI Rural Microgrid Intelligence System"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False

    API_V1_STR: str = "/api/v1"

    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]

    TOTAL_HOUSES: int = 10
    SOLAR_CAPACITY_KW: float = 30.0
    BATTERY_CAPACITY_KWH: float = 50.0
    BATTERY_INITIAL_SOC: float = 0.6

    # S3 — set in .env for production
    MODEL_S3_BUCKET: str = ""
    MODEL_S3_PREFIX: str = "models/latest/"

    # Twilio (optional)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    ENVIRONMENT: str = "development"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
