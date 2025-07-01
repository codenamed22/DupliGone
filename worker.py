#!/usr/bin/env python3
"""
Celery Worker Script for DupliGone Photo Processing
Run this script to start processing workers
"""

import os
import sys
from services.queue_service import celery_app

if __name__ == '__main__':
    # Set up logging
    import logging
    logging.basicConfig(level=logging.INFO)
    
    # Start the worker
    celery_app.start()
