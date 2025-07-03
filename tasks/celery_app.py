"""
Celery application configuration for DupliGone project.
Handles distributed task processing with Redis as message broker.
"""

from celery import Celery
import os

# Create Celery app instance
celery_app = Celery(
    "dupligone",
    broker=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    backend=os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    include=["tasks.image_tasks"]  # Include our task modules
)

# Configure Celery settings
celery_app.conf.update(
    # Serialization settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    
    # Timezone settings
    timezone="UTC",
    enable_utc=True,
    
    # Task routing - separate queues for different operations
    task_routes={
        "tasks.image_tasks.process_images_task": {"queue": "image_processing"},
        "tasks.image_tasks.cluster_images_task": {"queue": "clustering"},
    },
    
    # Worker settings for multithreading
    worker_concurrency=4,  # Number of concurrent worker processes
    worker_prefetch_multiplier=1,  # Tasks to prefetch per worker
    
    # Task execution settings
    task_acks_late=True,  # Acknowledge tasks after completion
    worker_disable_rate_limits=False,
    
    # Result backend settings
    result_expires=3600,  # Results expire after 1 hour
    result_persistent=True,
)

# Optional: Add periodic tasks if needed
celery_app.conf.beat_schedule = {
    # Example: cleanup old sessions every hour
    'cleanup-old-sessions': {
        'task': 'tasks.image_tasks.cleanup_old_sessions',
        'schedule': 3600.0,  # Every hour
    },
}
