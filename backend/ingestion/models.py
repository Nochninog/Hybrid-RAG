"""Структурное представление документа перед разбиением на фрагменты."""

from dataclasses import dataclass
from typing import Literal


BlockType = Literal["heading", "paragraph", "list", "table", "code"]


@dataclass(frozen=True)
class DocumentBlock:
    """Элемент документа; position начинается с 0, номера страниц — с 1."""

    position: int
    kind: BlockType
    text: str
    heading_level: int | None = None
    page_start: int | None = None
    page_end: int | None = None


@dataclass(frozen=True)
class ParsedDocument:
    """Блоки одного документа в исходном порядке."""

    document_id: int
    blocks: tuple[DocumentBlock, ...]


@dataclass(frozen=True)
class DocumentChunk:
    """Текст для векторизации вместе с заголовками и ссылкой на блоки."""

    document_id: int
    position: int
    text: str
    headings: tuple[str, ...]
    block_positions: tuple[int, ...]
    token_count: int
