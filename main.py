"""
FastAPI REST API for DupliGone project.
Handles image upload (POST /upload) and result retrieval (GET /getResult).
Mobile-first responsive API with token-based session management.
"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime
import os
import logging

# Import our custom modules
from models.database import db_manager, SessionModel, ImageModel
from services.azure_storage import azure_storage
from tasks.image_tasks import process_images_task

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create FastAPI app instance
app = FastAPI(
    title="DupliGone API", 
    version="1.0.0",
    description="Photo Library Cleaner - Remove duplicates intelligently"
)

# CORS middleware for mobile-first responsive design
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files for the web interface
app.mount("/static", StaticFiles(directory="static"), name="static")

# Pydantic models for API request/response
class UploadResponse(BaseModel):
    token: str
    session_id: str
    message: str
    total_images: int

class ImageInfo(BaseModel):
    image_id: str
    original_filename: str
    blob_url: str
    quality_score: float
    delete_recommended: bool
    cluster_id: Optional[str] = None
    metadata: Dict[str, Any] = {}

class ClusterInfo(BaseModel):
    cluster_id: str
    images: List[ImageInfo]
    best_image_id: str
    total_images: int

class ResultResponse(BaseModel):
    session_id: str
    status: str
    total_images: int
    processed_images: int
    clusters: List[ClusterInfo]
    recommendations: Dict[str, int]

class DeleteRequest(BaseModel):
    image_ids: List[str]

class DeleteResponse(BaseModel):
    message: str
    deleted_count: int

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    """Initialize database connection on startup"""
    await db_manager.connect()
    logger.info("Database connected successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Clean up database connection on shutdown"""
    await db_manager.disconnect()
    logger.info("Database disconnected")

# Helper function to validate file types
def is_valid_image(file: UploadFile) -> bool:
    """Check if uploaded file is a valid image"""
    valid_types = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/bmp', 'image/webp']
    return file.content_type in valid_types

# API Endpoints

@app.post("/upload", response_model=UploadResponse)
async def upload_images(files: List[UploadFile] = File(...)):
    """
    Upload multiple images and return processing token
    """
    try:
        logger.info(f"Received upload request with {len(files)} files")
        
        # Validate files
        valid_files = [f for f in files if is_valid_image(f)]
        if not valid_files:
            raise HTTPException(status_code=400, detail="No valid image files provided")
        
        if len(valid_files) != len(files):
            logger.warning(f"Filtered out {len(files) - len(valid_files)} invalid files")
        
        # Generate session ID and token
        session_id = str(uuid.uuid4())
        token = str(uuid.uuid4())
        
        logger.info(f"Created session {session_id} with token {token}")
        
        # **CRITICAL FIX: Connect to database**
        await db_manager.connect()
        
        # Create session in database
        session_data = SessionModel(
            session_id=session_id,
            public_key=token,
            status="uploading",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            total_images=len(valid_files)
        )
        await db_manager.create_session(session_data)
        
        # Upload files to Azure AND store in database
        uploaded_count = 0
        for i, file in enumerate(valid_files):
            try:
                logger.info(f"Uploading file {i+1}/{len(valid_files)}: {file.filename}")
                content = await file.read()
                blob_url = await azure_storage.upload_file(
                    content, file.filename or f"image_{i}.jpg", session_id
                )
                
                # **CRITICAL FIX: Store image in database immediately**
                image_data = ImageModel(
                    image_id=str(uuid.uuid4()),
                    session_id=session_id,
                    original_filename=file.filename or f"image_{i}.jpg",
                    blob_url=blob_url,  # Exact URL from Azure
                    hash_value="",  # Will be calculated by Celery
                    quality_score=0.0,  # Will be calculated by Celery
                    delete_recommended=False,
                    metadata={}
                )
                await db_manager.save_image(image_data)
                uploaded_count += 1
                
                logger.info(f"Successfully uploaded and stored: {blob_url}")
                
            except Exception as e:
                logger.error(f"Failed to upload {file.filename}: {str(e)}")
                # Continue with other files
        
        if uploaded_count == 0:
            raise HTTPException(status_code=500, detail="Failed to upload any files")
        
        # Update session status
        await db_manager.update_session(session_id, {
            "status": "uploaded",
            "total_images": uploaded_count
        })
        
        # **CRITICAL FIX: Only pass session_id to Celery task**
        logger.info(f"Starting background processing for {uploaded_count} images")
        process_images_task.delay(session_id)  # Remove uploaded_urls parameter
        
        return UploadResponse(
            token=token,
            session_id=session_id,
            message=f"Successfully uploaded {uploaded_count} images. Processing started.",
            total_images=uploaded_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
    finally:
        # **CRITICAL FIX: Always disconnect from database**
        await db_manager.disconnect()


@app.get("/getResult", response_model=ResultResponse)
async def get_results(authorization: str = Header(...)):
    """
    Get processing results using token
    Flow: UI calls with token -> return current status and results
    """
    try:
        # Extract token from Authorization header (Bearer token format)
        if not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Invalid authorization header format")
        
        token = authorization.replace("Bearer ", "")
        logger.info(f"Getting results for token: {token[:8]}...")
        
        # Find session by token
        session = await db_manager.db.sessions.find_one({"public_key": token})
        if not session:
            raise HTTPException(status_code=404, detail="Invalid token or session expired")
        
        session_id = session["session_id"]
        logger.info(f"Found session: {session_id}")
        
        # Get session images
        images = await db_manager.get_session_images(session_id)
        
        # Get clusters
        clusters = await db_manager.get_session_clusters(session_id)
        
        # Build cluster information with image details
        cluster_info = []
        for cluster in clusters:
            cluster_images = [img for img in images if img.image_id in cluster.images]
            cluster_info.append(ClusterInfo(
                cluster_id=cluster.cluster_id,
                images=[ImageInfo(**img.dict()) for img in cluster_images],
                best_image_id=cluster.best_image_id,
                total_images=len(cluster_images)
            ))
        
        # Calculate recommendations
        total_recommended_for_deletion = sum(1 for img in images if img.delete_recommended)
        space_saved_estimate = total_recommended_for_deletion * 2.5  # Rough MB estimate
        
        recommendations = {
            "total_images": len(images),
            "recommended_for_deletion": total_recommended_for_deletion,
            "clusters_found": len(clusters),
            "estimated_space_saved_mb": int(space_saved_estimate)
        }
        
        logger.info(f"Returning results: {session['status']}, {len(images)} images, {len(clusters)} clusters")
        
        return ResultResponse(
            session_id=session_id,
            status=session["status"],
            total_images=session["total_images"],
            processed_images=session.get("processed_images", 0),
            clusters=cluster_info,
            recommendations=recommendations
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get results: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get results: {str(e)}")

@app.post("/delete", response_model=DeleteResponse)
async def delete_images(
    delete_request: DeleteRequest,
    authorization: str = Header(...)
):
    """
    Delete selected images from both Azure storage and database
    """
    try:
        # Extract token and validate session
        token = authorization.replace("Bearer ", "")
        session = await db_manager.db.sessions.find_one({"public_key": token})
        if not session:
            raise HTTPException(status_code=404, detail="Invalid token")
        
        session_id = session["session_id"]
        logger.info(f"Deleting {len(delete_request.image_ids)} images for session {session_id}")
        
        # Get images to delete
        images_to_delete = []
        async for img in db_manager.db.images.find({
            "session_id": session_id,
            "image_id": {"$in": delete_request.image_ids}
        }):
            images_to_delete.append(img)
        
        if not images_to_delete:
            raise HTTPException(status_code=404, detail="No images found to delete")
        
        # Delete from Azure Blob Storage
        deleted_count = 0
        for img in images_to_delete:
            try:
                await azure_storage.delete_file(img["blob_url"])
                deleted_count += 1
                logger.info(f"Deleted from Azure: {img['original_filename']}")
            except Exception as e:
                logger.error(f"Failed to delete from Azure: {img['blob_url']}: {str(e)}")
        
        # Delete from database
        result = await db_manager.db.images.delete_many({
            "session_id": session_id,
            "image_id": {"$in": delete_request.image_ids}
        })
        
        logger.info(f"Deleted {result.deleted_count} images from database")
        
        return DeleteResponse(
            message=f"Successfully deleted {deleted_count} images",
            deleted_count=deleted_count
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete images: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to delete images: {str(e)}")

@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    return {
        "status": "healthy", 
        "timestamp": datetime.utcnow(),
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    """Redirect to static web interface"""
    return FileResponse("static/index.html")

# Development server runner
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8000)),
        reload=True,
        log_level="info"
    )


'''
What this FastAPI REST API does:


Core Endpoints:

POST /upload: Accepts multiple files, uploads to Azure, returns token
GET /getResult: Uses Bearer token to return processing status and results
POST /delete: Deletes selected images from both Azure and database




Token-Based Flow:

Upload → Generate session_id + token → Store in database → Return token to client
Processing → Background tasks update session status in database
Results → Client uses token to get current status and cluster results
Deletion → Client uses token to delete recommended images




Session Management:

Public key system: Each session gets unique token for API access
Status tracking: "uploading" → "uploaded" → "processing" → "clustering" → "completed"
Database integration: All session data stored in MongoDB




Mobile-First Features:

CORS enabled: Supports cross-origin requests for mobile apps
File validation: Checks image types before processing
Progress tracking: Returns processing progress for UI updates
Error handling: Robust error responses with proper HTTP codes




API Response Format:

All responses in JSON format as requested
Cluster information includes delete_recommended flags
Recommendations include space savings estimates



'''