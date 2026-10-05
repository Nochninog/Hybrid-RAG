"""Получение аргументов командной строки и вывод результата."""

import argparse
from pathlib import Path

from corpdb.documents.errors import DocumentValidationError
from corpdb.documents.validation import validate_document


def main() -> int:
    parser = argparse.ArgumentParser(description="Check document")
    parser.add_argument("file", type=Path, help="Путь к исходному документу")
    args = parser.parse_args()

    try:
        document = validate_document(args.file)
    except (DocumentValidationError, OSError) as exc:
        print(f"Ошибка: {exc}")
        return 1

    print(f"Файл: {document.original_filename}")
    print(f"Путь: {document.path}")
    print(f"Расширение: {document.extension}")
    print(f"Размер: {document.size_bytes} байт")
    print("Проверка пройдена. Сохранение оригинала ещё не подключено.")
    return 0
