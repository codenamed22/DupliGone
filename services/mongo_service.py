from pymongo import MongoClient
from pymongo.collection import Collection
from typing import Dict, List, Optional, Any
from datetime import datetime
from config.settings import settings
from models.session import Session, SessionStatus

class MongoService:
    def __init__(self):
        self.client = MongoClient(settings.mongo_uri)
        self.db = self.client[settings.mongo_db_name]
        
        # Collections
        self.sessions: Collection = self.db["sessions"]
        self.images: Collection = self.db["images"]
        self.clusters: Collection = self.db["clusters"]
        
        # Create indexes for better performance
        self._create_indexes()

    def _create_indexes(self):
        """Create database indexes for better query performance"""
        self.sessions.create_index("session_id", unique=True)
        self.sessions.create_index("created_at")
        self.images.create_index("session_id")
        self.images.create_index("cluster_id")
        self.clusters.create_index("session_id")

    # Session Management
    def create_session(self, session_id: str, s3_folder_path: str = None) -> Dict[str, Any]:
        """Create a new session"""
        session_data = {
            "session_id": session_id,
            "status": SessionStatus.CREATED.value,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "s3_folder_path": s3_folder_path,
            "total_images": 0,
            "processed_images": 0,
            "clusters_found": 0,
            "images_flagged_for_deletion": 0,
            "metadata": {}
        }
        
        result = self.sessions.insert_one(session_data)
        session_data["_id"] = str(result.inserted_id)
        return session_data

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session by ID"""
        session = self.sessions.find_one({"session_id": session_id})
        if session:
            session["_id"] = str(session["_id"])
        return session

    def update_session(self, session_id: str, update_data: Dict[str, Any]) -> bool:
        """Update session data"""
        update_data["updated_at"] = datetime.utcnow()
        result = self.sessions.update_one(
            {"session_id": session_id},
            {"$set": update_data}
        )
        return result.modified_count > 0

    def update_session_status(self, session_id: str, status: SessionStatus) -> bool:
        """Update session status"""
        return self.update_session(session_id, {"status": status.value})

    # Image Management
    def save_image(self, image_data: Dict[str, Any]) -> str:
        """Save image metadata"""
        image_data["created_at"] = datetime.utcnow()
        result = self.images.insert_one(image_data)
        return str(result.inserted_id)

    def get_images_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all images for a session"""
        images = list(self.images.find({"session_id": session_id}))
        for img in images:
            img["_id"] = str(img["_id"])
        return images

    def update_image(self, image_id: str, update_data: Dict[str, Any]) -> bool:
        """Update image metadata"""
        from bson import ObjectId
        result = self.images.update_one(
            {"_id": ObjectId(image_id)},
            {"$set": update_data}
        )
        return result.modified_count > 0

    # Cluster Management
    def save_cluster(self, cluster_data: Dict[str, Any]) -> str:
        """Save cluster data"""
        cluster_data["created_at"] = datetime.utcnow()
        result = self.clusters.insert_one(cluster_data)
        return str(result.inserted_id)

    def get_clusters_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """Get all clusters for a session"""
        clusters = list(self.clusters.find({"session_id": session_id}))
        for cluster in clusters:
            cluster["_id"] = str(cluster["_id"])
        return clusters

# Create global MongoDB service instance
mongo_service = MongoService()
