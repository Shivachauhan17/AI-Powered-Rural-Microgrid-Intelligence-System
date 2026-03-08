from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    APP_NAME: str = "AI Rural Microgrid Intelligence System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # API
    API_V1_STR: str = "/api/v1"
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_USE_OPENSSL_RAND_HEX_32"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:5173"]
    
    # Database (future)
    DATABASE_URL: str = "sqlite:///./microgrid.db"
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # AWS
    AWS_REGION: str = "ap-south-1"
    AWS_S3_BUCKET: str = "microgrid-data"
    AWS_IOT_ENDPOINT: str = ""
    
    # Microgrid Config
    TOTAL_HOUSES: int = 10
    SOLAR_CAPACITY_KW: float = 30.0      # Total solar panel capacity kW
    BATTERY_CAPACITY_KWH: float = 50.0   # Battery storage kWh
    BATTERY_INITIAL_SOC: float = 0.6     # State of charge 0-1
    
    # Priority multipliers for fairness
    PRIORITY_CLINIC: float = 1.0         # Always gets full power
    PRIORITY_SCHOOL: float = 0.9
    PRIORITY_PUMP: float = 0.85
    PRIORITY_HOUSEHOLD: float = 0.7
    
    # SMS (Twilio)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
