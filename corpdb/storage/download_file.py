from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)

from corpdb.storage.client import create_client
from corpdb.storage.errors import UploadError


def download_file( bucket, storage_key):
    try:
        s3 = create_client()
      
        return s3.get_object(Bucket=bucket, Key=storage_key)
    
    except EndpointConnectionError as e:
        raise UploadError("MinIO недоступен") from e

    except NoCredentialsError as e:
        raise UploadError("Не заданы MINIO_USERNAME / MINIO_PASSWORD в .env") from e

    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        msg = e.response.get("Error", {}).get("Message", str(e))
        if code == "NoSuchBucket":
            raise UploadError(f"Бакет '{bucket}' не существует.") from e
        if code == "AccessDenied":
            raise UploadError(
                f"Доступ запрещён к бакету '{bucket}'. Проверьте ключи."
            ) from e
        raise UploadError(f"Ошибка MinIO [{code}]: {msg}") from e

    except BotoCoreError as e:
        raise UploadError(f"Ошибка boto3: {e}") from e
