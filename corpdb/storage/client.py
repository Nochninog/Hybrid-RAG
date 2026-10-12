import os

import boto3
from botocore.client import Config
from dotenv import load_dotenv


def create_client():
    load_dotenv()

    MINIO_USERNAME = os.getenv("MINIO_USERNAME")
    MINIO_PASSWORD = os.getenv("MINIO_PASSWORD")
    MINIO_URL = os.getenv("MINIO_URL")

    s3 = boto3.client(
        "s3",
        endpoint_url=MINIO_URL,
        aws_access_key_id=MINIO_USERNAME,
        aws_secret_access_key=MINIO_PASSWORD,
        config=Config(signature_version="s3v4"),
    )

    return s3
