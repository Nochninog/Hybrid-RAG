"""Проверка локального файла перед сохранением оригинала."""

from pathlib import Path

from backend.documents.errors import DocumentValidationError
from backend.documents.models import ValidatedDocument
from backend.documents.policy import ALLOWED_EXTENSIONS, MAX_FILE_SIZE


def validate_document(file_path: Path) -> ValidatedDocument:
    """Проверить наличие, расширение и размер файла, вернуть метаданные."""
    abs_path = file_path.resolve()

    if not abs_path.is_file():
        raise DocumentValidationError("Document not exist")

    if abs_path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise DocumentValidationError("Document has wrong suffix")

    file_size = abs_path.stat().st_size
    if file_size <= 0 or file_size > MAX_FILE_SIZE:
        raise DocumentValidationError("Incorrect document size")

    return ValidatedDocument(
        path=abs_path,
        original_filename=abs_path.name,
        extension=abs_path.suffix.lower(),
        size_bytes=file_size,
    )
