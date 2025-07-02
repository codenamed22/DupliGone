import os
from typing import List
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    # ADDED azure removed s3
    azure_storage_connection_string: str = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
    azure_container_name: str = os.getenv("AZURE_CONTAINER_NAME", "photos")

    
    # MongoDB Configuration
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db_name: str = os.getenv("MONGO_DB_NAME", "dupligone_db")
    
    # Redis Configuration
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # Application Settings
    secret_key: str = os.getenv("SECRET_KEY", "change-this-secret-key")
    debug: bool = os.getenv("DEBUG", "True").lower() == "true"
    upload_max_size: str = os.getenv("UPLOAD_MAX_SIZE", "50MB")
    allowed_extensions: List[str] = os.getenv("ALLOWED_EXTENSIONS", "jpg,jpeg,png,gif,bmp,tiff,webp").split(",")
    
    # Processing Settings
    similarity_threshold: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.85"))
    cluster_min_samples: int = int(os.getenv("CLUSTER_MIN_SAMPLES", "2"))
    quality_weights_sharpness: float = float(os.getenv("QUALITY_WEIGHTS_SHARPNESS", "0.4"))
    quality_weights_exposure: float = float(os.getenv("QUALITY_WEIGHTS_EXPOSURE", "0.3"))
    quality_weights_faces: float = float(os.getenv("QUALITY_WEIGHTS_FACES", "0.3"))
    
    # Celery Configuration
    celery_broker_url: str = redis_url
    celery_result_backend: str = redis_url
    
    class Config:
        env_file = ".env"

# Create global settings instance
settings = Settings()
