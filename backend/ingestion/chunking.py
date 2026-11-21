"""Сборка структурных блоков в фрагменты с ограничением по токенам."""

from collections.abc import Callable
from dataclasses import replace

from backend.ingestion.models import DocumentChunk, ParsedDocument
from backend.ingestion.tokenization import count_tokens as qwen_count_tokens


def chunk_document(
    document: ParsedDocument,
    max_tokens: int = 512,
    count_tokens: Callable[[str], int] = qwen_count_tokens,
    *,
    short_chunk_tokens: int = 16,
) -> tuple[DocumentChunk, ...]:
    """Считает полный текст с заголовками. Перекрытия между фрагментами нет.

    count_tokens должен использовать токенизатор модели и учитывать те же
    специальные токены, что и запрос векторизации. Заголовки без содержимого
    не образуют отдельного фрагмента. Короткий фрагмент присоединяется к
    следующему, если вместе они помещаются. Внутренние заголовки сохраняются.
    """
    if max_tokens < 1:
        raise ValueError("max_tokens должен быть положительным")
    chunks = []
    headings: list[tuple[int, str]] = []
    parts: list[str] = []
    positions: list[int] = []

    def render(body: str) -> str:
        prefix = "\n".join(text for _, text in headings)
        return prefix + "\n\n" + body if prefix else body

    def fits(body: str) -> bool:
        return count_tokens(render(body)) <= max_tokens

    def flush() -> None:
        if parts:
            text = render("\n\n".join(parts))
            chunks.append(DocumentChunk(
                document.document_id, len(chunks), text,
                tuple(text for _, text in headings), tuple(positions),
                count_tokens(text),
            ))
            parts.clear()
            positions.clear()

    def split(text: str):
        if fits(text):
            yield text
            return
        if len(text) <= 1:
            raise ValueError("Лимит слишком мал для заголовков и текста блока")
        middle = len(text) // 2
        # Разрезаем по пробельной границе; длинное слово — по символам Unicode.
        boundary = max(text.rfind(" ", 0, middle), text.rfind("\n", 0, middle))
        cut = boundary + 1 if boundary >= 0 else middle
        yield from split(text[:cut])
        yield from split(text[cut:])

    for block in document.blocks:
        if block.kind == "heading":
            flush()
            level = block.heading_level
            if level is None or level < 1:
                raise ValueError("У заголовка должен быть положительный уровень")
            headings = [(n, text) for n, text in headings if n < level]
            headings.append((level, block.text))
            continue
        if not block.text.strip():
            continue
        candidate = "\n\n".join([*parts, block.text])
        if fits(candidate):
            parts.append(block.text)
            positions.append(block.position)
            continue
        flush()
        for piece in split(block.text):
            # Части одного блока склеиваем без добавления новых символов.
            if parts and not fits(parts[0] + piece):
                flush()
            if parts:
                parts[0] += piece
            else:
                parts.append(piece)
                positions.append(block.position)
    flush()
    merged: list[DocumentChunk] = []
    for chunk in chunks:
        if merged and merged[-1].token_count < short_chunk_tokens:
            previous = merged[-1]
            text = previous.text + "\n\n" + chunk.text
            size = count_tokens(text)
            if size <= max_tokens:
                # Для разных разделов в метаданных оставляем общий путь.
                headings_path = previous.headings
                while chunk.headings[:len(headings_path)] != headings_path:
                    headings_path = headings_path[:-1]
                merged[-1] = replace(
                    previous, text=text, headings=headings_path, token_count=size,
                    block_positions=tuple(dict.fromkeys(
                        previous.block_positions + chunk.block_positions)),
                )
                continue
        merged.append(replace(chunk, position=len(merged)))
    return tuple(merged)
