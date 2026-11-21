"""Объекты данных, которыми обмениваются функции модуля документов."""

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidatedDocument:
    """Метаданные проверенного файла; оригинал ещё не сохранён."""

    path: Path
    original_filename: str
    extension: str
    size_bytes: int
