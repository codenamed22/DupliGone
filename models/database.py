from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import MongoClient
import os
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel

# Session model to track user sessions and processing status
class SessionModel(BaseModel):
    session_id: str
    public_key: str
    status: str  # "uploading", "processing", "completed", "failed"
    created_at: datetime
    updated_at: datetime
    total_images: Optional[int] = 0
    processed_images: Optional[int] = 0
    clusters: Optional[List[Dict[str, Any]]] = []

# Image model to store metadata about each uploaded image
class ImageModel(BaseModel):
    image_id: str
    session_id: str
    original_filename: str
    blob_url: str
    hash_value: str
    cluster_id: Optional[str] = None
    quality_score: float
    delete_recommended: bool = False
    metadata: Dict[str, Any] = {}

# Cluster model to group similar images
class ClusterModel(BaseModel):
    cluster_id: str
    session_id: str
    images: List[str]  # List of image_ids
    best_image_id: str
    created_at: datetime

# Database manager to handle connections and CRUD operations
class DatabaseManager:
    def __init__(self):
        self.client = None
        self.db = None
        
    async def connect(self):
        self.client = AsyncIOMotorClient(os.getenv("MONGODB_URL"))
        self.db = self.client[os.getenv("DATABASE_NAME")]
        
    async def disconnect(self):
        if self.client:
            self.client.close()
            
    async def create_session(self, session_data: SessionModel) -> str:
        result = await self.db.sessions.insert_one(session_data.dict())
        return str(result.inserted_id)
        
    async def get_session(self, session_id: str) -> Optional[SessionModel]:
        session = await self.db.sessions.find_one({"session_id": session_id})
        return SessionModel(**session) if session else None
        
    async def update_session(self, session_id: str, update_data: Dict[str, Any]):
        await self.db.sessions.update_one(
            {"session_id": session_id},
            {"$set": {**update_data, "updated_at": datetime.utcnow()}}
        )
        
    async def save_image(self, image_data: ImageModel):
        await self.db.images.insert_one(image_data.dict())
        
    async def get_session_images(self, session_id: str) -> List[ImageModel]:
        cursor = self.db.images.find({"session_id": session_id})
        images = await cursor.to_list(length=None)
        return [ImageModel(**img) for img in images]
        
    async def save_cluster(self, cluster_data: ClusterModel):
        await self.db.clusters.insert_one(cluster_data.dict())
        
    async def get_session_clusters(self, session_id: str) -> List[ClusterModel]:
        cursor = self.db.clusters.find({"session_id": session_id})
        clusters = await cursor.to_list(length=None)
        return [ClusterModel(**cluster) for cluster in clusters]

db_manager = DatabaseManager()

"""
Database models and manager for DupliGone project.
Handles user sessions, image metadata, and clustering information.

What this database module does:

SessionModel:

Tracks each user's session with a unique ID and token

Stores processing status (uploading → processing → completed)

Keeps count of total and processed images

Maintains timestamps for session management

ImageModel:

Stores metadata for each uploaded image

Links to Azure Blob Storage URL

Contains perceptual hash for duplicate detection

Tracks quality score and deletion recommendations

Associates images with clusters

ClusterModel:

Groups similar images together

Identifies the best image in each cluster

Links back to the session that created it

DatabaseManager:

Handles async MongoDB connections

Provides CRUD operations for all models

Manages session lifecycle and image processing workflow

Uses Motor (async MongoDB driver) for non-blocking database operations

"""