from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from typing import List, Dict, Any, Optional
import uuid
import os
import shutil
from datetime import datetime
import asyncio

# Import our services and models
from config.settings import settings
from services.azure_blob_service import azure_blob_service as blob_service
from services.mongo_service import mongo_service
from services.queue_service import queue_service
from models.session import Session, SessionStatus
from models.image import ImageUpload, ImageMetadata
from models.cluster import Cluster

# Create FastAPI app
app = FastAPI(
    title="DupliGone Photo Library Cleaner",
    description="AI-powered duplicate photo detection and removal service",
    version="1.0.0"
)

# Add CORS middleware for mobile-first approach
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure this properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend/templates")

# =====================================================
# FRONTEND ROUTES (Mobile-First Web Interface)
# =====================================================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Main page - mobile-first photo upload interface"""
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/results/{session_id}", response_class=HTMLResponse)
async def results_page(request: Request, session_id: str):
    """Results page showing clusters and deletion recommendations"""
    return templates.TemplateResponse("results.html", {
        "request": request, 
        "session_id": session_id
    })

# =====================================================
# SESSION MANAGEMENT APIs
# =====================================================

@app.post("/api/v1/sessions", response_model=Dict[str, str])
async def create_session():
    """Create a new photo processing session"""
    session_id = str(uuid.uuid4())
    
    try:
        # Create session in database
        session_data = mongo_service.create_session(session_id)
        
        return {
            "session_id": session_id,
            "status": "created",
            "message": "Session created successfully",
            "upload_url": f"/api/v1/sessions/{session_id}/upload",
            "results_url": f"/api/v1/sessions/{session_id}/results"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create session: {str(e)}")

@app.get("/api/v1/sessions/{session_id}", response_model=Dict[str, Any])
async def get_session(session_id: str):
    """Get session details and processing status"""
    session = mongo_service.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return {
        "session_id": session_id,
        "status": session["status"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "total_images": session.get("total_images", 0),
        "processed_images": session.get("processed_images", 0),
        "clusters_found": session.get("clusters_found", 0),
        "images_flagged_for_deletion": session.get("images_flagged_for_deletion", 0),
        "metadata": session.get("metadata", {})
    }

@app.delete("/api/v1/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a session and all associated data"""
    session = mongo_service.get_session(session_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    try:
        # Get all images for cleanup
        images = mongo_service.get_images_by_session(session_id)
        
        # Delete S3 objects
        for image in images:
            try:
                blob_service.delete_object(image['blob_name'])
            except Exception as e:
                print(f"Warning: Failed to delete S3 object {image['s3_path']}: {e}")
        
        # Delete database records
        mongo_service.images.delete_many({"session_id": session_id})
        mongo_service.clusters.delete_many({"session_id": session_id})
        mongo_service.sessions.delete_one({"session_id": session_id})
        
        return {"message": "Session deleted successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete session: {str(e)}")

# =====================================================
# FILE UPLOAD APIs
# =====================================================

@app.post("/api/v1/sessions/{session_id}/upload")
async def upload_images(
    session_id: str,
    files: List[UploadFile] = File(...),
    background_tasks: BackgroundTasks = None
):
    """Upload multiple images for processing"""
    # Verify session exists
    session = mongo_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Check file count limit
    if len(files) > 100:  # Reasonable limit
        raise HTTPException(status_code=400, detail="Too many files. Maximum 100 files allowed.")
    
    # Update session status to uploading
    mongo_service.update_session_status(session_id, SessionStatus.UPLOADING)
    
    uploaded_files = []
    temp_dir = f"temp/{session_id}"
    os.makedirs(temp_dir, exist_ok=True)
    
    try:
        for file in files:
            # Validate file type
            if not file.content_type or not file.content_type.startswith('image/'):
                raise HTTPException(status_code=400, detail=f"File {file.filename} is not an image")
            
            # Check file size (50MB limit)
            file_content = await file.read()
            if len(file_content) > 50 * 1024 * 1024:  # 50MB
                raise HTTPException(status_code=400, detail=f"File {file.filename} is too large. Maximum 50MB allowed.")
            
            # Save file temporarily
            file_path = f"{temp_dir}/{file.filename}"
            with open(file_path, "wb") as buffer:
                buffer.write(file_content)
            
            # changed for azure accordingly
            blob_name = f"{session_id}/{file.filename}"
            blob_url = blob_service.upload_file(file_path, blob_name)
            
            # Save image metadata to database 
            #changed for azure blob fields
            image_data = {
            "session_id": session_id,
            "filename": file.filename,
            "blob_name": blob_name,  # Changed from s3_path
            "blob_url": blob_url,    # Changed from s3_url
            "file_size": len(file_content),
            "content_type": file.content_type,
            "upload_timestamp": datetime.utcnow(),
            "delete_recommended": False,
            "processed": False
         }
            
            image_id = mongo_service.save_image(image_data)
            uploaded_files.append({
                "image_id": image_id,
                "filename": file.filename,
                "blob_url": blob_url,              #changed for azure blob url
                "file_size": len(file_content)
            })
            
            # Clean up temp file
            os.remove(file_path)
        
        # Update session with upload info
        mongo_service.update_session(session_id, {
            "total_images": len(uploaded_files),
            "s3_folder_path": session_id,
            "status": SessionStatus.CREATED.value  # Ready for processing
        })
        
        # Start processing job
        job_id = queue_service.add_image_processing_job(session_id)
        
        # Clean up temp directory
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        return {
            "session_id": session_id,
            "uploaded_files": uploaded_files,
            "total_files": len(uploaded_files),
            "job_id": job_id,
            "status": "uploaded",
            "message": "Files uploaded successfully, processing started",
            "results_url": f"/results/{session_id}",
            "api_results_url": f"/api/v1/sessions/{session_id}/results"
        }
        
    except Exception as e:
        # Clean up on error
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        
        # Update session status
        mongo_service.update_session_status(session_id, SessionStatus.FAILED)
        
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")

# =====================================================
# PROCESSING RESULTS APIs
# =====================================================

@app.get("/api/v1/sessions/{session_id}/results")
async def get_processing_results(session_id: str):
    """Get processing results including clusters and recommendations"""
    session = mongo_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get all images for this session
    images = mongo_service.get_images_by_session(session_id)
    
    # Get clusters
    clusters = mongo_service.get_clusters_by_session(session_id)
    
    # Organize results by cluster
    result_clusters = []
    unclustered_images = []
    
    for cluster in clusters:
        cluster_images = [img for img in images if img.get('cluster_id') == cluster.get('cluster_id')]
        
        if cluster_images:
            best_image = next((img for img in cluster_images if img.get('is_best_in_cluster', False)), cluster_images[0])
            images_to_delete = [img for img in cluster_images if img.get('delete_recommended', False)]
            
            result_clusters.append({
                "cluster_id": cluster.get('cluster_id'),
                "image_count": len(cluster_images),
                "best_image": {
                    "image_id": best_image['_id'],
                    "filename": best_image['filename'],
                    "s3_url": best_image.get('s3_url', ''),
                    "quality_score": best_image.get('quality_overall', 0),
                    "file_size": best_image.get('file_size', 0)
                },
                "images_to_delete": [
                    {
                        "image_id": img['_id'],
                        "filename": img['filename'],
                        "s3_url": img.get('s3_url', ''),
                        "quality_score": img.get('quality_overall', 0),
                        "file_size": img.get('file_size', 0)
                    } for img in images_to_delete
                ],
                "all_images": [
                    {
                        "image_id": img['_id'],
                        "filename": img['filename'],
                        "s3_url": img.get('s3_url', ''),
                        "quality_score": img.get('quality_overall', 0),
                        "file_size": img.get('file_size', 0),
                        "delete_recommended": img.get('delete_recommended', False),
                        "is_best": img.get('is_best_in_cluster', False)
                    } for img in cluster_images
                ]
            })
    
    # Find unclustered images (unique images)
    clustered_image_ids = set()
    for cluster in result_clusters:
        for img in cluster["all_images"]:
            clustered_image_ids.add(img["image_id"])
    
    for img in images:
        if img['_id'] not in clustered_image_ids:
            unclustered_images.append({
                "image_id": img['_id'],
                "filename": img['filename'],
                "blob_url": best_image.get('blob_url', '')      #changed for azure
                "quality_score": img.get('quality_overall', 0),
                "file_size": img.get('file_size', 0)
            })
    
    return {
        "session_id": session_id,
        "status": session["status"],
        "total_images": session.get("total_images", 0),
        "processed_images": session.get("processed_images", 0),
        "clusters_found": len(result_clusters),
        "images_flagged_for_deletion": session.get("images_flagged_for_deletion", 0),
        "unique_images": len(unclustered_images),
        "clusters": result_clusters,
        "unique_images_list": unclustered_images,
        "processing_metadata": session.get("metadata", {}),
        "potential_space_saved": sum(
            sum(img["file_size"] for img in cluster["images_to_delete"])
            for cluster in result_clusters
        )
    }

@app.get("/api/v1/sessions/{session_id}/clusters")
async def get_clusters(session_id: str):
    """Get all clusters for a session"""
    session = mongo_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    clusters = mongo_service.get_clusters_by_session(session_id)
    return {
        "session_id": session_id,
        "clusters": clusters
    }

@app.get("/api/v1/sessions/{session_id}/images")
async def get_images(session_id: str):
    """Get all images for a session"""
    session = mongo_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    images = mongo_service.get_images_by_session(session_id)
    return {
        "session_id": session_id,
        "images": images
    }

# =====================================================
# IMAGE MANAGEMENT APIs
# =====================================================

@app.patch("/api/v1/images/{image_id}/flag")
async def toggle_delete_flag(image_id: str, delete_recommended: bool):
    """Toggle delete recommendation flag for an image"""
    success = mongo_service.update_image(image_id, {
        "delete_recommended": delete_recommended,
        "user_modified": True,
        "modified_at": datetime.utcnow()
    })
    
    if not success:
        raise HTTPException(status_code=404, detail="Image not found")
    
    return {
        "image_id": image_id,
        "delete_recommended": delete_recommended,
        "message": "Flag updated successfully"
    }

@app.post("/api/v1/sessions/{session_id}/confirm-deletions")
async def confirm_deletions(session_id: str):
    """Confirm deletion of flagged images"""
    session = mongo_service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Get images flagged for deletion
    images = mongo_service.get_images_by_session(session_id)
    images_to_delete = [img for img in images if img.get('delete_recommended', False)]
    
    if not images_to_delete:
        return {
            "session_id": session_id,
            "deleted_count": 0,
            "message": "No images flagged for deletion"
        }
    
    deleted_count = 0
    total_space_freed = 0
    
    for image in images_to_delete:
        try:
            # changed for azure
            blob_service.delete_object(image['blob_name'])
            
            # Mark as deleted in database
            mongo_service.update_image(image['_id'], {
                "deleted": True,
                "deleted_at": datetime.utcnow()
            })
            
            deleted_count += 1
            total_space_freed += image.get('file_size', 0)
            
        except Exception as e:
            print(f"Failed to delete image {image['filename']}: {e}")
    
    return {
        "session_id": session_id,
        "deleted_count": deleted_count,
        "total_flagged": len(images_to_delete),
        "space_freed_bytes": total_space_freed,
        "space_freed_mb": round(total_space_freed / (1024 * 1024), 2),
        "message": f"Successfully deleted {deleted_count} images, freed {round(total_space_freed / (1024 * 1024), 2)} MB"
    }

# =====================================================
# JOB STATUS APIs
# =====================================================

@app.get("/api/v1/jobs/{job_id}/status")
async def get_job_status(job_id: str):
    """Get processing job status"""
    job_status = queue_service.get_job_status(job_id)
    return job_status

# =====================================================
# HEALTH CHECK APIs
# =====================================================

@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test database connection
        mongo_service.sessions.find_one({})
        db_status = "healthy"
    except:
        db_status = "unhealthy"
    
    try:
        # Test Redis connection
        import redis
        r = redis.from_url(settings.redis_url)
        r.ping()
        redis_status = "healthy"
    except:
        redis_status = "unhealthy"
    
    return {
        "status": "healthy" if db_status == "healthy" and redis_status == "healthy" else "unhealthy",
        "timestamp": datetime.utcnow(),
        "version": "1.0.0",
        "services": {
            "database": db_status,
            "redis": redis_status
        }
    }

@app.get("/")
async def root():
    """Root endpoint redirect to main interface"""
    return {
        "message": "DupliGone Photo Library Cleaner API",
        "version": "1.0.0",
        "web_interface": "/",
        "api_docs": "/docs",
        "health": "/api/v1/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
