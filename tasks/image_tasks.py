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

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@celery_app.task(bind=True, name="tasks.image_tasks.process_images_task")
def process_images_task(self, session_id: str, image_urls: List[str]):
    """
    Process images with multithreading for hashing and quality assessment
    Two threads work simultaneously: one for hashing, one for quality assessment
    """
    
    async def process_single_image(image_url: str, filename: str) -> Dict[str, Any]:
        """Process a single image with both hashing and quality assessment"""
        try:
            logger.info(f"Processing image: {filename}")
            
            # Download image from Azure Blob
            image_bytes = await azure_storage.download_file(image_url)
            
            # Use ThreadPoolExecutor for CPU-intensive image analysis
            with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
                # Submit both tasks simultaneously
                hash_future = executor.submit(
                    image_processor.calculate_perceptual_hashes, 
                    image_bytes
                )
                quality_future = executor.submit(
                    image_processor.calculate_quality_metrics, 
                    image_bytes
                )
                
                # Wait for both to complete
                hashes = hash_future.result()
                metrics = quality_future.result()
            
            # Calculate overall quality score
            quality_score = image_processor.calculate_overall_quality(metrics)
            
            # Determine if image should be recommended for deletion
            delete_recommended = quality_score < float(os.getenv("QUALITY_THRESHOLD", "0.5"))
            
            return {
                "image_id": str(uuid.uuid4()),
                "session_id": session_id,
                "original_filename": filename,
                "blob_url": image_url,
                "hash_value": hashes["combined"],  # Use combined pHash + dHash
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
            }
        except Exception as e:
            logger.error(f"Error processing image {image_url}: {str(e)}")
            return None
    
    async def process_all_images():
        """Process all images concurrently with progress tracking"""
        await db_manager.connect()
        
        try:
            # Update session status to processing
            await db_manager.update_session(session_id, {
                "status": "processing",
                "processed_images": 0
            })
            
            # Process images with multithreading
            logger.info(f"Starting processing of {len(image_urls)} images")
            
            # Create tasks for concurrent processing
            tasks = []
            for i, url in enumerate(image_urls):
                filename = f"image_{i}.jpg"  # Extract actual filename if needed
                tasks.append(process_single_image(url, filename))
            
            # Process images in batches to avoid overwhelming the system
            batch_size = int(os.getenv("MAX_CONCURRENT_PROCESSING", "4"))
            processed_images = []
            
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i:i + batch_size]
                
                # Process batch concurrently
                batch_results = await asyncio.gather(*batch, return_exceptions=True)
                
                # Save successful results and update progress
                for result in batch_results:
                    if result and not isinstance(result, Exception):
                        image_model = ImageModel(**result)
                        await db_manager.save_image(image_model)
                        processed_images.append(result)
                        
                        # Update progress
                        await db_manager.update_session(session_id, {
                            "processed_images": len(processed_images)
                        })
                        
                        logger.info(f"Processed {len(processed_images)}/{len(image_urls)} images")
            
            # Update session status
            await db_manager.update_session(session_id, {
                "status": "clustering",
                "processed_images": len(processed_images)
            })
            
            logger.info(f"Completed processing {len(processed_images)} images")
            
            # Trigger clustering task
            cluster_images_task.delay(session_id, [img["hash_value"] for img in processed_images])
            
        except Exception as e:
            logger.error(f"Error in process_all_images: {str(e)}")
            await db_manager.update_session(session_id, {"status": "failed"})
        finally:
            await db_manager.disconnect()
    
    # Run the async function
    asyncio.run(process_all_images())

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
    
    # Run the async function
    asyncio.run(perform_clustering())

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
    
    asyncio.run(cleanup())

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