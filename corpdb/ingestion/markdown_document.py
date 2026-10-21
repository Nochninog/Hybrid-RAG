"""Разбор Markdown в структурные блоки документа."""

from markdown_it import MarkdownIt

from corpdb.ingestion.models import BlockType, DocumentBlock, ParsedDocument


def parse_markdown(document_id: int, text: str) -> ParsedDocument:
    """Сохраняет разметку блоков; у заголовков отделяет уровень от текста."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    tokens = MarkdownIt("commonmark").enable("table").parse(text)
    kinds: dict[str, BlockType] = {
        "heading_open": "heading",
        "paragraph_open": "paragraph",
        "bullet_list_open": "list",
        "ordered_list_open": "list",
        "table_open": "table",
        "fence": "code",
        "code_block": "code",
        "blockquote_open": "paragraph",
        "html_block": "paragraph",
        "hr": "paragraph",
    }
    blocks = []
    consumed_until = 0
    for index, token in enumerate(tokens):
        if token.map is None or token.type not in kinds:
            continue
        start, end = token.map
        if start < consumed_until:
            continue
        kind = kinds[token.type]
        heading_level = None
        if kind == "heading":
            content = tokens[index + 1].content
            heading_level = int(token.tag[1:])
        else:
            content = "\n".join(lines[start:end]).rstrip("\n")
        blocks.append(DocumentBlock(len(blocks), kind, content, heading_level))
        consumed_until = end
    return ParsedDocument(document_id, tuple(blocks))
