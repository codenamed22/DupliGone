"""
Azure Blob Storage service for DupliGone project.
Handles uploading images to cloud storage, downloading for processing,
and cleaning up deleted images.
"""

from azure.storage.blob import BlobServiceClient
from azure.storage.blob.aio import BlobServiceClient as AsyncBlobServiceClient
import os
import aiofiles
from typing import List, BinaryIO
import uuid

class AzureStorageService:
    def __init__(self):
        # Get Azure connection details from environment variables
        self.connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        self.container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")
        
        # Create the blob service client for sync operations
        self.blob_service_client = BlobServiceClient.from_connection_string(
            self.connection_string
        )
        
    async def upload_file(self, file_content: bytes, filename: str, session_id: str) -> str:
        """
        Upload a file to Azure Blob Storage
        Creates a unique blob name using session_id and UUID to avoid conflicts
        """
        # Create unique blob name: session_id/uuid_original_filename
        blob_name = f"{session_id}/{uuid.uuid4()}_{filename}"
        
        # Use async client for non-blocking upload
        async with AsyncBlobServiceClient.from_connection_string(
            self.connection_string
        ) as blob_service_client:
            blob_client = blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=blob_name
            )
            # Upload the file content, overwrite if exists
            await blob_client.upload_blob(file_content, overwrite=True)
            
        return blob_client.url
        
    async def download_file(self, blob_url: str) -> bytes:
        """
        Download a file from Azure Blob Storage
        Used by image processing service to get images for analysis
        """
        # Extract blob name from the full URL
        blob_name = blob_url.split('/')[-1]
        
        async with AsyncBlobServiceClient.from_connection_string(
            self.connection_string
        ) as blob_service_client:
            blob_client = blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=blob_name
            )
            # Download the blob content as bytes
            stream = await blob_client.download_blob()
            return await stream.readall()
            
    async def delete_file(self, blob_url: str):
        """
        Delete a file from Azure Blob Storage
        Used when user confirms deletion of recommended images
        """
        # Extract blob name from URL
        blob_name = blob_url.split('/')[-1]
        
        async with AsyncBlobServiceClient.from_connection_string(
            self.connection_string
        ) as blob_service_client:
            blob_client = blob_service_client.get_blob_client(
                container=self.container_name, 
                blob=blob_name
            )
            # Delete the blob
            await blob_client.delete_blob()
            
    async def list_session_files(self, session_id: str) -> List[str]:
        """
        List all files for a specific session
        Useful for cleanup operations or downloading clean library
        """
        blob_urls = []
        
        async with AsyncBlobServiceClient.from_connection_string(
            self.connection_string
        ) as blob_service_client:
            container_client = blob_service_client.get_container_client(
                self.container_name
            )
            
            # List all blobs with the session_id prefix
            async for blob in container_client.list_blobs(name_starts_with=f"{session_id}/"):
                blob_client = blob_service_client.get_blob_client(
                    container=self.container_name,
                    blob=blob.name
                )
                blob_urls.append(blob_client.url)
                
        return blob_urls
        
    async def cleanup_session(self, session_id: str):
        """
        Delete all files for a session (cleanup after processing)
        Used for session cleanup or when user wants to delete everything
        """
        async with AsyncBlobServiceClient.from_connection_string(
            self.connection_string
        ) as blob_service_client:
            container_client = blob_service_client.get_container_client(
                self.container_name
            )
            
            # Delete all blobs for this session
            async for blob in container_client.list_blobs(name_starts_with=f"{session_id}/"):
                blob_client = blob_service_client.get_blob_client(
                    container=self.container_name,
                    blob=blob.name
                )
                await blob_client.delete_blob()

# Create a global instance to use throughout the application
azure_storage = AzureStorageService()

'''

-> keeps storage seperate from processing



What this Azure Storage service does:

File Organization:

Organizes files by session_id to keep user data separate
Uses UUID to prevent filename conflicts
Creates URLs that can be stored in database and accessed later

Async Operations:

All operations are async to prevent blocking the API
Uses Azure's async client for better performance
Handles multiple file uploads/downloads concurrently

Key Methods:

upload_file() - Stores user uploaded images in cloud
download_file() - Gets images back for processing (pHash/dHash analysis)
delete_file() - Removes images user wants to delete
list_session_files() - Gets all files for a session (for clean library download)
cleanup_session() - Removes all session data (privacy/cleanup)

Storage Flow:

User uploads → upload_file() → Returns Azure URL
Processing needs image → download_file() → Gets image bytes for analysis
User deletes recommended → delete_file() → Removes from cloud
Session ends → cleanup_session() → Cleans up everything
'''