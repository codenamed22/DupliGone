import os
import shutil
from typing import Dict, List, Any
from datetime import datetime
from celery import current_task

from services.queue_service import celery_app
from services.s3_service import s3_service
from services.mongo_service import mongo_service
from processing.hashing import image_hasher
from processing.quality import quality_assessor
from processing.clustering import image_clusterer
from models.session import SessionStatus

@celery_app.task(bind=True, name='process_images_task')
def process_images_task(self, session_id: str):
    """
    Main task to process uploaded images:
    1. Download images from S3
    2. Compute perceptual hashes
    3. Perform quality assessment
    4. Cluster similar images
    5. Mark low-quality images for deletion
    6. Update database with results
    """
    try:
        # Update session status to processing
        mongo_service.update_session_status(session_id, SessionStatus.PROCESSING)
        
        # Update task progress
        current_task.update_state(
            state='PROGRESS',
            meta={'current': 0, 'total': 100, 'status': 'Starting image processing...'}
        )
        
        # Step 1: Get session and images from database
        session = mongo_service.get_session(session_id)
        if not session:
            raise Exception(f"Session {session_id} not found")
        
        images = mongo_service.get_images_by_session(session_id)
        if not images:
            raise Exception(f"No images found for session {session_id}")
        
        total_images = len(images)
        current_task.update_state(
            state='PROGRESS',
            meta={'current': 10, 'total': 100, 'status': f'Found {total_images} images to process'}
        )
        
        # Step 2: Download images from S3 to local temp directory
        temp_dir = f"temp/{session_id}_processing"
        os.makedirs(temp_dir, exist_ok=True)
        
        local_image_paths = {}
        for i, image in enumerate(images):
            try:
                local_path = os.path.join(temp_dir, image['filename'])
                s3_service.download_file(image['s3_path'], local_path)
                local_image_paths[image['_id']] = local_path
                
                # Update progress
                progress = 10 + (i + 1) / total_images * 20  # 10-30%
                current_task.update_state(
                    state='PROGRESS',
                    meta={'current': int(progress), 'total': 100, 'status': f'Downloaded {i+1}/{total_images} images'}
                )
            except Exception as e:
                print(f"Failed to download {image['filename']}: {e}")
                continue
        
        if not local_image_paths:
            raise Exception("No images could be downloaded for processing")
        
        # Step 3: Compute perceptual hashes for all images
        current_task.update_state(
            state='PROGRESS',
            meta={'current': 30, 'total': 100, 'status': 'Computing image hashes...'}
        )
        
        image_hashes = {}
        image_combined_hashes = {}
        
        for i, (image_id, local_path) in enumerate(local_image_paths.items()):
            try:
                # Compute combined hashes for better clustering
                combined_hash = image_hasher.compute_combined_hash(local_path)
                image_combined_hashes[image_id] = combined_hash
                
                # Use average hash as primary hash
                image_hashes[image_id] = combined_hash['ahash']
                
                # Update image in database with hash
                mongo_service.update_image(image_id, {
                    'hash_ahash': combined_hash['ahash'],
                    'hash_dhash': combined_hash['dhash'],
                    'hash_whash': combined_hash['whash']
                })
                
                # Update progress
                progress = 30 + (i + 1) / len(local_image_paths) * 20  # 30-50%
                current_task.update_state(
                    state='PROGRESS',
                    meta={'current': int(progress), 'total': 100, 'status': f'Computed hashes for {i+1}/{len(local_image_paths)} images'}
                )
            except Exception as e:
                print(f"Failed to compute hash for {local_path}: {e}")
                continue
        
        # Step 4: Perform quality assessment
        current_task.update_state(
            state='PROGRESS',
            meta={'current': 50, 'total': 100, 'status': 'Assessing image quality...'}
        )
        
        image_qualities = {}
        for i, (image_id, local_path) in enumerate(local_image_paths.items()):
            try:
                quality_data = quality_assessor.calculate_overall_quality(local_path)
                image_qualities[image_id] = quality_data
                
                # Update image in database with quality scores
                mongo_service.update_image(image_id, {
                    'quality_sharpness': quality_data['sharpness'],
                    'quality_exposure': quality_data['exposure'],
                    'quality_face_count': quality_data['face_count'],
                    'quality_face_score': quality_data['face_score'],
                    'quality_overall': quality_data['overall_score']
                })
                
                # Update progress
                progress = 50 + (i + 1) / len(local_image_paths) * 20  # 50-70%
                current_task.update_state(
                    state='PROGRESS',
                    meta={'current': int(progress), 'total': 100, 'status': f'Assessed quality for {i+1}/{len(local_image_paths)} images'}
                )
            except Exception as e:
                print(f"Failed to assess quality for {local_path}: {e}")
                continue
        
        # Step 5: Cluster similar images
        current_task.update_state(
            state='PROGRESS',
            meta={'current': 70, 'total': 100, 'status': 'Clustering similar images...'}
        )
        
        # Use combined hashes for better clustering
        clusters = image_clusterer.cluster_by_combined_hashes(image_combined_hashes)
        
        # Filter out noise clusters (label -1 from DBSCAN)
        valid_clusters = {k: v for k, v in clusters.items() if k != -1 and len(v) > 1}
        
        current_task.update_state(
            state='PROGRESS',
            meta={'current': 80, 'total': 100, 'status': f'Found {len(valid_clusters)} clusters of similar images'}
        )
        
        # Step 6: Process each cluster and mark images for deletion
        images_flagged_for_deletion = 0
        
        for cluster_id, image_ids in valid_clusters.items():
            try:
                # Get local paths for images in this cluster
                cluster_paths = [local_image_paths[img_id] for img_id in image_ids if img_id in local_image_paths]
                
                if len(cluster_paths) < 2:
                    continue
                
                # Find the best quality image in the cluster
                best_image_path = quality_assessor.find_best_image(cluster_paths)
                best_image_id = None
                
                # Find the image_id corresponding to the best path
                for img_id, path in local_image_paths.items():
                    if path == best_image_path:
                        best_image_id = img_id
                        break
                
                # Save cluster information
                cluster_data = {
                    'session_id': session_id,
                    'cluster_id': str(cluster_id),
                    'image_ids': image_ids,
                    'best_image_id': best_image_id,
                    'similarity_threshold': image_clusterer.similarity_threshold,
                    'image_count': len(image_ids)
                }
                mongo_service.save_cluster(cluster_data)
                
                # Mark non-best images for deletion
                for img_id in image_ids:
                    if img_id != best_image_id:
                        mongo_service.update_image(img_id, {
                            'delete_recommended': True,
                            'cluster_id': str(cluster_id),
                            'is_best_in_cluster': False
                        })
                        images_flagged_for_deletion += 1
                    else:
                        mongo_service.update_image(img_id, {
                            'delete_recommended': False,
                            'cluster_id': str(cluster_id),
                            'is_best_in_cluster': True
                        })
                
            except Exception as e:
                print(f"Error processing cluster {cluster_id}: {e}")
                continue
        
        # Step 7: Update session with final results
        current_task.update_state(
            state='PROGRESS',
            meta={'current': 90, 'total': 100, 'status': 'Finalizing results...'}
        )
        
        # Calculate statistics
        cluster_stats = image_clusterer.get_cluster_statistics(valid_clusters)
        
        # Update session with processing results
        mongo_service.update_session(session_id, {
            'status': SessionStatus.COMPLETED.value,
            'processed_images': len(local_image_paths),
            'clusters_found': len(valid_clusters),
            'images_flagged_for_deletion': images_flagged_for_deletion,
            'metadata': {
                'processing_completed_at': datetime.utcnow(),
                'cluster_statistics': cluster_stats,
                'total_processed': len(local_image_paths),
                'hashing_successful': len(image_hashes),
                'quality_assessment_successful': len(image_qualities)
            }
        })
        
        # Step 8: Cleanup temporary files
        try:
            shutil.rmtree(temp_dir)
        except Exception as e:
            print(f"Warning: Failed to cleanup temp directory {temp_dir}: {e}")
        
        # Final update
        current_task.update_state(
            state='SUCCESS',
            meta={
                'current': 100,
                'total': 100,
                'status': 'Processing completed successfully',
                'result': {
                    'session_id': session_id,
                    'total_images': total_images,
                    'processed_images': len(local_image_paths),
                    'clusters_found': len(valid_clusters),
                    'images_flagged_for_deletion': images_flagged_for_deletion,
                    'cluster_statistics': cluster_stats
                }
            }
        )
        
        return {
            'session_id': session_id,
            'status': 'completed',
            'total_images': total_images,
            'processed_images': len(local_image_paths),
            'clusters_found': len(valid_clusters),
            'images_flagged_for_deletion': images_flagged_for_deletion
        }
        
    except Exception as e:
        # Update session status to failed
        mongo_service.update_session_status(session_id, SessionStatus.FAILED)
        mongo_service.update_session(session_id, {
            'metadata': {
                'error': str(e),
                'failed_at': datetime.utcnow()
            }
        })
        
        # Cleanup on error
        temp_dir = f"temp/{session_id}_processing"
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except:
                pass
        
        # Update task state
        current_task.update_state(
            state='FAILURE',
            meta={'error': str(e), 'session_id': session_id}
        )
        
        raise Exception(f"Image processing failed for session {session_id}: {e}")
