from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
)

from corpdb.storage.client import create_client
from corpdb.storage.errors import UploadError


def upload_file(file_path, bucket, file_name):
    try:
        s3 = create_client()
        with open(file_path, "rb") as f:
            resp = s3.put_object(Bucket=bucket, Key=file_name, Body=f)

        version_id = resp.get("VersionId")
        return {"bucket": bucket, "key": file_name, "version_id": version_id}
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
