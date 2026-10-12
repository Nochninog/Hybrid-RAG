from pathlib import Path

from corpdb.documents.models import ValidatedDocument
from corpdb.documents.validation import validate_document
from corpdb.storage.upload_file import upload_file


def upload_document(
    file_path: Path, bucket: str = "corpdb-originals"
) -> tuple[ValidatedDocument, dict[str, str | None]]:
    document = validate_document(file_path)
    result = upload_file(document.path, bucket, document.original_filename)
    return document, result
