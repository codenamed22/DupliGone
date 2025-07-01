import boto3
import os
from typing import List
from botocore.exceptions import ClientError
from config.settings import settings

class S3Service:
    def __init__(self):
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region
        )
        self.bucket_name = settings.s3_bucket_name

    def upload_file(self, file_path: str, object_name: str) -> str:
        """Upload a file to S3 bucket"""
        try:
            self.s3_client.upload_file(file_path, self.bucket_name, object_name)
            return f"s3://{self.bucket_name}/{object_name}"
        except ClientError as e:
            raise Exception(f"Failed to upload file to S3: {e}")

    def download_file(self, object_name: str, download_path: str) -> bool:
        """Download a file from S3 bucket"""
        try:
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(download_path), exist_ok=True)
            self.s3_client.download_file(self.bucket_name, object_name, download_path)
            return True
        except ClientError as e:
            raise Exception(f"Failed to download file from S3: {e}")

    def list_objects(self, prefix: str) -> List[str]:
        """List objects in S3 bucket with given prefix"""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=prefix
            )
            return [obj['Key'] for obj in response.get('Contents', [])]
        except ClientError as e:
            raise Exception(f"Failed to list S3 objects: {e}")

    def delete_object(self, object_name: str) -> bool:
        """Delete an object from S3 bucket"""
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=object_name)
            return True
        except ClientError as e:
            raise Exception(f"Failed to delete S3 object: {e}")

# Create global S3 service instance
s3_service = S3Service()
