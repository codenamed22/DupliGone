"""
Cleanup script for DupliGone: removes old sessions, images, clusters from MongoDB and deletes orphaned blobs from Azure Blob Storage.

- Deletes sessions older than a given threshold (default: 7 days)
- Deletes all images and clusters associated with those sessions
- Deletes blobs in Azure container that are not referenced in the database

Usage:
    python cleanup.py [--days 7]
"""
import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables if needed
load_dotenv()

# Import your database and Azure storage modules
from models.database import db_manager
from services.azure_storage import azure_storage

DAYS = int(os.getenv("CLEANUP_DAYS", 7))

async def cleanup_old_sessions(days=DAYS):
    cutoff = datetime.utcnow() - timedelta(days=days)
    print(f"Cleaning up sessions older than {days} days (before {cutoff})...")

    # Find old sessions
    old_sessions = db_manager.db.sessions.find({"created_at": {"$lt": cutoff}})
    session_ids = [s["session_id"] async for s in old_sessions]
    if not session_ids:
        print("No old sessions found.")
        return
    print(f"Found {len(session_ids)} old sessions.")

    # Delete images and clusters for these sessions
    del_images = await db_manager.db.images.delete_many({"session_id": {"$in": session_ids}})
    del_clusters = await db_manager.db.clusters.delete_many({"session_id": {"$in": session_ids}})
    del_sessions = await db_manager.db.sessions.delete_many({"session_id": {"$in": session_ids}})
    print(f"Deleted {del_images.deleted_count} images, {del_clusters.deleted_count} clusters, {del_sessions.deleted_count} sessions.")

async def cleanup_orphaned_blobs():
    print("Checking for orphaned blobs in Azure...")
    # Get all blob URLs from DB
    all_images = db_manager.db.images.find({})
    db_blobs = set([img["blob_url"] async for img in all_images])
    # List all blobs in Azure
    azure_blobs = set(await azure_storage.list_all_blobs())
    # Find blobs not referenced in DB
    orphaned = azure_blobs - db_blobs
    print(f"Found {len(orphaned)} orphaned blobs.")
    for blob_url in orphaned:
        try:
            await azure_storage.delete_file(blob_url)
            print(f"Deleted orphaned blob: {blob_url}")
        except Exception as e:
            print(f"Failed to delete blob {blob_url}: {e}")

async def main():
    await db_manager.connect()
    await cleanup_old_sessions()
    await cleanup_orphaned_blobs()
    await db_manager.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
