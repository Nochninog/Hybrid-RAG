from botocore.exceptions import BotoCoreError, ClientError

from corpdb.storage.client import create_client
from corpdb.storage.errors import DeleteError


def delete_file(bucket: str, storage_key: str) -> None:
    try:
        s3 = create_client()
        s3.delete_object(
            Bucket=bucket,
            Key=storage_key,
        )
    except (BotoCoreError, ClientError) as exc:
        raise DeleteError(
            "Не удалось удалить объект из MinIO"
        ) from exc