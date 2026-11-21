"""Получение аргументов командной строки и вывод результата."""

import argparse
from pathlib import Path

from openai import OpenAIError
from weaviate.exceptions import WeaviateBaseError

from backend.documents.errors import DocumentValidationError
from backend.documents.operations import upload_document
from backend.storage.errors import UploadError

from backend.database.errors import DatabaseError

from backend.ingestion.index_document import index_document
from backend.ingestion.errors import ExtractionError

def main() -> int:
    parser = argparse.ArgumentParser(description="Загрузка и индексация документа")
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

        index_run_id = index_document(document_id, extension=document.extension)
        print(f"Индексация завершена. Метка набора: {index_run_id}")
    except (
        DocumentValidationError,
        UploadError,
        DatabaseError,
        ExtractionError,
        OpenAIError,
        WeaviateBaseError,
        ValueError,
        OSError,
    ) as exc:
        print(f"Ошибка: {exc}")
        return 1

    return 0
