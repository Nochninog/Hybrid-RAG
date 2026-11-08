"""Индексация разделов сохранённой Wiki-страницы в Weaviate."""

from uuid import UUID

from corpdb.database.read_wiki_page import read_wiki_page
from corpdb.embeddings.qwen import embed_texts
from corpdb.indexes.client import create_connection
from corpdb.indexes.insert_wiki_chunk import delete_extra_wiki_chunks, insert_wiki_chunk
from corpdb.wiki.chunking import chunk_wiki_page


def index_wiki_page(wiki_page_id: int, max_tokens: int = 512) -> tuple[UUID, ...]:
    """Возвращает UUID всех записанных фрагментов; ошибки передаются вызывающему."""
    title, content = read_wiki_page(wiki_page_id)
    chunks = chunk_wiki_page(wiki_page_id, title, content, max_tokens)
    vectors = embed_texts([chunk.text for chunk in chunks]) if chunks else []
    if len(vectors) != len(chunks):
        raise ValueError("Число векторов не совпадает с числом Wiki-фрагментов")
    with create_connection() as client:
        ids = tuple(insert_wiki_chunk(chunk, vector, client=client)
                    for chunk, vector in zip(chunks, vectors))
        delete_extra_wiki_chunks(wiki_page_id, len(chunks), client=client)
    return ids
