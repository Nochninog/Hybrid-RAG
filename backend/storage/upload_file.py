from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)

from backend.storage.client import create_client
from backend.storage.errors import UploadError


def upload_file(file_path, bucket, storage_key):
    try:
        s3 = create_client()
        with open(file_path, "rb") as f:
            s3.put_object(Bucket=bucket, Key=storage_key, Body=f)

        return {"bucket": bucket, "key": storage_key}
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

    except OSError as e:
        raise UploadError(f"Не удалось прочитать файл '{file_path}': {e}") from e
