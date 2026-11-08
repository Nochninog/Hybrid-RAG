"""Разделы Wiki и деление длинных разделов на фрагменты."""

from collections.abc import Callable
from dataclasses import dataclass, replace

from corpdb.ingestion.chunking import chunk_document
from corpdb.ingestion.markdown_document import parse_markdown
from corpdb.ingestion.models import DocumentBlock, ParsedDocument
from corpdb.ingestion.tokenization import count_tokens as qwen_count_tokens


@dataclass(frozen=True)
class WikiChunk:
    wiki_page_id: int
    position: int
    title: str
    headings: tuple[str, ...]
    text: str
    token_count: int


def chunk_wiki_page(
    wiki_page_id: int,
    title: str,
    content: str,
    max_tokens: int = 512,
    count_tokens: Callable[[str], int] = qwen_count_tokens,
) -> tuple[WikiChunk, ...]:
    """Название и путь заголовков входят в текст и лимит каждого фрагмента."""
    blocks = parse_markdown(wiki_page_id, content).blocks
    # Одинаковые название страницы и первый H1 не дублируем в контексте.
    if blocks and blocks[0].kind == "heading" and blocks[0].heading_level == 1 and blocks[0].text == title:
        blocks = blocks[1:]
    # Название страницы становится корнем для всех заголовков Markdown.
    document = ParsedDocument(wiki_page_id, (
        DocumentBlock(0, "heading", title, 1),
        *(replace(block, position=i + 1,
                  heading_level=block.heading_level + 1 if block.heading_level else None)
          for i, block in enumerate(blocks)),
    ))
    chunks = chunk_document(document, max_tokens, count_tokens, short_chunk_tokens=0)
    return tuple(WikiChunk(
        wiki_page_id, chunk.position, title, chunk.headings, chunk.text, chunk.token_count,
    ) for chunk in chunks)
