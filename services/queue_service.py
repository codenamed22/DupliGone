from celery import Celery
from config.settings import settings

# Create Celery app
celery_app = Celery(
    'dupligone',
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=['tasks.process_images']
)

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

class QueueService:
    def __init__(self):
        self.celery = celery_app

    def add_image_processing_job(self, session_id: str) -> str:
        """Add image processing job to queue"""
        from tasks.process_images import process_images_task
        
        result = process_images_task.delay(session_id)
        return result.id

    def get_job_status(self, job_id: str) -> dict:
        """Get job status and result"""
        result = celery_app.AsyncResult(job_id)
        return {
            "job_id": job_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
            "traceback": result.traceback if result.failed() else None
        }

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a job"""
        celery_app.control.revoke(job_id, terminate=True)
        return True

# Create global queue service instance
queue_service = QueueService()
