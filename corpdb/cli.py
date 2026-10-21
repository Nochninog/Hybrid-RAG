"""Получение аргументов командной строки и вывод результата."""

import argparse
from pathlib import Path

from corpdb.documents.errors import DocumentValidationError
from corpdb.documents.operations import upload_document
from corpdb.storage.errors import UploadError

from corpdb.database.errors import DatabaseError

from corpdb.ingestion.operations import process_document
from corpdb.ingestion.errors import ExtractionError

def main() -> int:
    parser = argparse.ArgumentParser(description="Check document")
    parser.add_argument("file", type=Path, help="Путь к исходному документу")
    args = parser.parse_args()

    try:
        document, result, document_id = upload_document(args.file)

        print(f"Файл: {document.original_filename}")
        print(f"Путь: {document.path}")
        print(f"Расширение: {document.extension}")
        print(f"Размер: {document.size_bytes} байт")
        print(result)
        print(document_id)

        chunks = process_document(document_id, extension=document.extension)
        for chunk in chunks:
            print(f"Фрагмент {chunk.position + 1} ({chunk.token_count} токенов):")
            print(chunk.text)
    except (
        DocumentValidationError,
        UploadError,
        DatabaseError,
        ExtractionError,
        OSError,
    ) as exc:
        print(f"Ошибка: {exc}")
        return 1

    return 0
