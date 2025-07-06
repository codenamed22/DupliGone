from azure.storage.blob import generate_blob_sas, BlobSasPermissions
from datetime import datetime, timedelta
import os
from urllib.parse import urlparse

def generate_sas_url(blob_url: str, expiry_minutes: int = 60) -> str:
    """
    Generate a SAS URL for a given blob URL, valid for expiry_minutes.
    """
    connection_string = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
    container_name = os.getenv("AZURE_STORAGE_CONTAINER_NAME")
    parsed = urlparse(blob_url)
    blob_name = parsed.path.split(f"/{container_name}/", 1)[-1].lstrip("/")

    from azure.storage.blob import BlobServiceClient
    blob_service_client = BlobServiceClient.from_connection_string(connection_string)
    account_name = blob_service_client.account_name
    account_key = blob_service_client.credential.account_key

    sas_token = generate_blob_sas(
        account_name=account_name,
        container_name=container_name,
        blob_name=blob_name,
        account_key=account_key,
        permission=BlobSasPermissions(read=True),
        expiry=datetime.utcnow() + timedelta(minutes=expiry_minutes)
    )
    base_url = f"https://{account_name}.blob.core.windows.net/{container_name}/{blob_name}"
    return f"{base_url}?{sas_token}"
