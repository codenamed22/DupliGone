"""
Celery tasks for image processing in DupliGone project.
Handles background processing with multithreading for hashing and quality assessment.
"""

from celery import Celery
from tasks.celery_app import celery_app
from services.image_processing import image_processor
from services.azure_storage import azure_storage
from models.database import db_manager, ImageModel, ClusterModel
import asyncio
import uuid
from datetime import datetime, timedelta
from typing import List, Dict, Any
import concurrent.futures
import threading
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="tasks.image_tasks.process_images_task")
def process_images_task(self, session_id: str):  # Remove image_urls parameter
    """
    Process images by querying database for session images
    """
    
    async def process_single_image(image: ImageModel) -> Dict[str, Any]:
        """Process a single image with both hashing and quality assessment"""
        try:
            logger.info(f"Processing image: {image.original_filename}")
            logger.info(f"Blob URL: {image.blob_url}")
            
            # Download image from Azure Blob
            image_bytes = await azure_storage.download_file(image.blob_url)
            
            # Use ThreadPoolExecutor for CPU-intensive image analysis
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                hash_future = executor.submit(
                    image_processor.calculate_perceptual_hashes, 
                    image_bytes
                )
                quality_future = executor.submit(
                    image_processor.calculate_quality_metrics, 
                    image_bytes
                )
                
                hashes = hash_future.result()
                metrics = quality_future.result()
            
            # Calculate overall quality score
            quality_score = image_processor.calculate_overall_quality(metrics)
            delete_recommended = quality_score < float(os.getenv("QUALITY_THRESHOLD", "0.5"))
            
            # Update the existing image record
            await db_manager.db.images.update_one(
                {"image_id": image.image_id},
                {"$set": {
                    "hash_value": hashes["combined"],
                    "quality_score": quality_score,
                    "delete_recommended": delete_recommended,
                    "metadata": {
                        "phash": hashes["phash"],
                        "dhash": hashes["dhash"],
                        "sharpness": metrics["sharpness"],
                        "brightness": metrics["brightness"],
                        "contrast": metrics["contrast"],
                        "face_count": metrics["face_count"]
                    }
                }}
            )
            
            return {
                "image_id": image.image_id,
                "hash_value": hashes["combined"],
                "quality_score": quality_score
            }
            
        except Exception as e:
            logger.error(f"Error processing image {image.blob_url}: {str(e)}")
            return None
    
    async def process_all_images():
        """Process all images for the session"""
        await db_manager.connect()
        
        try:
            # **CRITICAL FIX: Get images from database, not from parameters**
            images = await db_manager.get_session_images(session_id)
            
            if not images:
                logger.warning(f"No images found for session {session_id}")
                return
            
            logger.info(f"Starting processing of {len(images)} images")
            
            # Update session status
            await db_manager.update_session(session_id, {
                "status": "processing",
                "processed_images": 0
            })
            
            # Process images in batches
            batch_size = int(os.getenv("MAX_CONCURRENT_PROCESSING", "4"))
            processed_count = 0
            hash_values = []
            
            for i in range(0, len(images), batch_size):
                batch = images[i:i + batch_size]
                
                # Create tasks for batch
                tasks = [process_single_image(img) for img in batch]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Process results
                for result in batch_results:
                    if result and not isinstance(result, Exception):
                        processed_count += 1
                        hash_values.append(result["hash_value"])
                        
                        # Update progress
                        await db_manager.update_session(session_id, {
                            "processed_images": processed_count
                        })
                        
                        logger.info(f"Processed {processed_count}/{len(images)} images")
            
            # Update session status
            await db_manager.update_session(session_id, {
                "status": "clustering",
                "processed_images": processed_count
            })
            
            logger.info(f"Completed processing {processed_count} images")
            
            # Trigger clustering
            cluster_images_task.delay(session_id, hash_values)
            
        except Exception as e:
            logger.error(f"Error in process_all_images: {str(e)}")
            await db_manager.update_session(session_id, {"status": "failed"})
        finally:
            await db_manager.disconnect()
    
    # Run async function
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(process_all_images())

@celery_app.task(bind=True, name="tasks.image_tasks.cluster_images_task")
def cluster_images_task(self, session_id: str, hash_values: List[str]):
    """
    Cluster similar images using DBSCAN with automatic eps detection
    Identifies best images in each cluster and marks others for deletion
    """
    
    async def perform_clustering():
        """Perform clustering and identify best images"""
        await db_manager.connect()
        
        try:
            logger.info(f"Starting clustering for session {session_id}")
            
            # Get all images for this session
            images = await db_manager.get_session_images(session_id)
            
            if len(images) < 2:
                logger.info("Less than 2 images, skipping clustering")
                await db_manager.update_session(session_id, {"status": "completed"})
                return
            
            # Create hash to image mapping
            hash_to_image = {img.hash_value: img for img in images}
            hash_list = list(hash_to_image.keys())
            
            # Perform clustering with automatic eps detection
            logger.info("Performing DBSCAN clustering with elbow method")
            clusters = image_processor.cluster_similar_images(hash_list, use_combined=True)
            
            logger.info(f"Found {len(clusters)} clusters")
            
            # Process each cluster
            cluster_count = 0
            for i, cluster_indices in enumerate(clusters):
                if len(cluster_indices) > 1:  # Only process clusters with multiple images
                    cluster_count += 1
                    cluster_id = str(uuid.uuid4())
                    cluster_images = [images[idx] for idx in cluster_indices]
                    
                    # Find best image in cluster (highest quality score)
                    best_image = max(cluster_images, key=lambda x: x.quality_score)
                    
                    logger.info(f"Cluster {cluster_count}: {len(cluster_images)} images, best quality: {best_image.quality_score:.3f}")
                    
                    # Mark other images for deletion
                    for img in cluster_images:
                        if img.image_id != best_image.image_id:
                            # Update image to mark for deletion
                            await db_manager.db.images.update_one(
                                {"image_id": img.image_id},
                                {"$set": {"delete_recommended": True, "cluster_id": cluster_id}}
                            )
                        else:
                            # Update best image with cluster ID
                            await db_manager.db.images.update_one(
                                {"image_id": img.image_id},
                                {"$set": {"cluster_id": cluster_id}}
                            )
                    
                    # Save cluster information
                    cluster_model = ClusterModel(
                        cluster_id=cluster_id,
                        session_id=session_id,
                        images=[img.image_id for img in cluster_images],
                        best_image_id=best_image.image_id,
                        created_at=datetime.utcnow()
                    )
                    await db_manager.save_cluster(cluster_model)
            
            # Update session status to completed
            await db_manager.update_session(session_id, {
                "status": "completed",
                "clusters": cluster_count
            })
            
            logger.info(f"Clustering completed: {cluster_count} duplicate groups found")
            
        except Exception as e:
            logger.error(f"Error in clustering: {str(e)}")
            await db_manager.update_session(session_id, {"status": "failed"})
        finally:
            await db_manager.disconnect()
    
    # Run the async function safely in Celery context
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(perform_clustering())

@celery_app.task(name="tasks.image_tasks.cleanup_old_sessions")
def cleanup_old_sessions():
    """
    Periodic task to cleanup old sessions and their associated data
    Runs every hour to free up storage space
    """
    
    async def cleanup():
        await db_manager.connect()
        
        try:
            # Find sessions older than 24 hours
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            
            old_sessions = await db_manager.db.sessions.find({
                "created_at": {"$lt": cutoff_time}
            }).to_list(length=None)
            
            for session in old_sessions:
                session_id = session["session_id"]
                logger.info(f"Cleaning up old session: {session_id}")
                
                # Delete from Azure Storage
                await azure_storage.cleanup_session(session_id)
                
                # Delete from database
                await db_manager.db.images.delete_many({"session_id": session_id})
                await db_manager.db.clusters.delete_many({"session_id": session_id})
                await db_manager.db.sessions.delete_one({"session_id": session_id})
                
            logger.info(f"Cleaned up {len(old_sessions)} old sessions")
            
        except Exception as e:
            logger.error(f"Error in cleanup: {str(e)}")
        finally:
            await db_manager.disconnect()
    
    # Run the async function safely in Celery context
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.run_until_complete(cleanup())


'''

What this Celery task system does:

Multithreading Architecture:

2 threads simultaneously: One for hashing (pHash+dHash), one for quality assessment
ThreadPoolExecutor: Manages concurrent CPU-intensive operations
Batch processing: Processes images in configurable batches to avoid overload



Task Queue System:

Separate queues: Different queues for processing vs clustering
Progress tracking: Updates database with processing progress
Error handling: Robust error handling with fallbacks



Background Processing Flow:

Upload → process_images_task starts
Multithreading → Hash calculation + Quality assessment run simultaneously
Progress updates → Database updated with processing status
Clustering trigger → Automatically starts clustering when processing done
DBSCAN with elbow → Finds optimal eps and clusters similar images
Results → Marks low-quality images with delete_recommended flag



Session Management:

Automatic cleanup: Removes old sessions after 24 hours
Storage cleanup: Cleans both database and Azure storage
Status tracking: "uploading" → "processing" → "clustering" → "completed"

'''