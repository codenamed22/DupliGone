from config.settings import settings

# Broker settings
broker_url = settings.redis_url
result_backend = settings.redis_url

# Task settings
task_serializer = 'json'
accept_content = ['json']
result_serializer = 'json'
timezone = 'UTC'
enable_utc = True

# Worker settings
worker_prefetch_multiplier = 1
worker_max_tasks_per_child = 1000
task_acks_late = True
task_reject_on_worker_lost = True

# Task execution settings
task_time_limit = 30 * 60  # 30 minutes
task_soft_time_limit = 25 * 60  # 25 minutes
task_track_started = True

# Result backend settings
result_expires = 3600  # 1 hour

# Routing
task_routes = {
    'process_images_task': {'queue': 'image_processing'},
}

# Queue configuration
task_default_queue = 'default'
task_queues = {
    'default': {
        'exchange': 'default',
        'routing_key': 'default',
    },
    'image_processing': {
        'exchange': 'image_processing',
        'routing_key': 'image_processing',
    },
}
