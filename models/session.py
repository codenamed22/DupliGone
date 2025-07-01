from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum

class SessionStatus(str, Enum):
    CREATED = "created"
    UPLOADING = "uploading" 
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class Session(BaseModel):
    session_id: str = Field(..., description="Unique session identifier")
    status: SessionStatus = SessionStatus.CREATED
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    s3_folder_path: Optional[str] = None
    total_images: int = 0
    processed_images: int = 0
    clusters_found: int = 0
    images_flagged_for_deletion: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        use_enum_values = True
