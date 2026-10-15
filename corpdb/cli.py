"""Получение аргументов командной строки и вывод результата."""

import argparse
from pathlib import Path

from corpdb.documents.errors import DocumentValidationError
from corpdb.documents.operations import upload_document
from corpdb.storage.errors import UploadError

from corpdb.database.errors import DatabaseError

def main() -> int:
    parser = argparse.ArgumentParser(description="Check document")
    parser.add_argument("file", type=Path, help="Путь к исходному документу")
    args = parser.parse_args()

    try:
        document, result, document_id = upload_document(args.file)
    except (
        DocumentValidationError,
        UploadError,
        DatabaseError,
        OSError,
    ) as exc:
        print(f"Ошибка: {exc}")
        return 1

    print(f"Файл: {document.original_filename}")
    print(f"Путь: {document.path}")
    print(f"Расширение: {document.extension}")
    print(f"Размер: {document.size_bytes} байт")
    print(result)
    print(document_id)
    return 0
