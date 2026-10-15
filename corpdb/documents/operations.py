from pathlib import Path
from uuid import uuid4

from corpdb.database.documents import insert_document
from corpdb.documents.models import ValidatedDocument
from corpdb.documents.validation import validate_document
from corpdb.storage.upload_file import upload_file
import logging

from corpdb.storage.delete_file import delete_file
from corpdb.storage.errors import DeleteError
from corpdb.database.errors import DatabaseWriteError

logger = logging.getLogger(__name__)

def upload_document(
    file_path: Path, bucket: str = "corpdb-originals"
) -> tuple[ValidatedDocument, dict[str, str | None], int]:
    document = validate_document(file_path)

    storage_key = f"{uuid4().hex}{document.extension}"
    storage_info = upload_file(
        document.path,
        bucket,
        storage_key,
    )

    try:
        document_id, old_storage_key = insert_document(
            filename=document.original_filename,
            storage_bucket=storage_info["bucket"],
            storage_key=storage_info["key"],
            size_bytes=document.size_bytes,
        )
    except DatabaseWriteError:
        try:
            delete_file(
                storage_info["bucket"],
                storage_info["key"],
            )
        except DeleteError:
            logger.warning(
                "Метаданные не записаны, но новый объект "
                "MinIO не удалось удалить: bucket=%s, key=%s",
                storage_info["bucket"],
                storage_info["key"],
            )

        raise

    if old_storage_key is not None:
        try:
            delete_file(
                storage_info["bucket"],
                old_storage_key,
            )
        except DeleteError:
            logger.warning(
                "Документ %s сохранён, но старый объект "
                "MinIO не удалён: bucket=%s, key=%s",
                document_id,
                storage_info["bucket"],
                old_storage_key,
            )

    return document, storage_info, document_id
