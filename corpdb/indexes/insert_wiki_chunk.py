"""Запись Wiki-фрагмента; повторный вызов заменяет тот же объект."""

from uuid import NAMESPACE_URL, UUID, uuid5

from weaviate import WeaviateClient
from weaviate.classes.query import Filter
from weaviate.exceptions import WeaviateBaseError

from corpdb.wiki.chunking import WikiChunk


def insert_wiki_chunk(chunk: WikiChunk, vector: list[float], *, client: WeaviateClient) -> UUID:
    chunk_id = uuid5(NAMESPACE_URL, f"corpdb:wiki-chunk:{chunk.wiki_page_id}:{chunk.position}")
    collection = client.collections.use("WikiChunk")
    properties = {
        "wiki_page_id": chunk.wiki_page_id,
        "position": chunk.position,
        "title": chunk.title,
        "headings": list(chunk.headings),
        "text": chunk.text,
        "token_count": chunk.token_count,
    }
    if collection.data.exists(chunk_id):
        collection.data.replace(uuid=chunk_id, properties=properties, vector={"qwen": vector})
    else:
        collection.data.insert(uuid=chunk_id, properties=properties, vector={"qwen": vector})
    return chunk_id


def delete_extra_wiki_chunks(wiki_page_id: int, chunk_count: int, *, client: WeaviateClient) -> None:
    """После полной записи удаляет хвост прежнего разбиения только этой страницы."""
    where = (Filter.by_property("wiki_page_id").equal(wiki_page_id)
             & Filter.by_property("position").greater_or_equal(chunk_count))
    collection = client.collections.use("WikiChunk")
    while True:
        result = collection.data.delete_many(where=where)
        if result.failed:
            raise WeaviateBaseError("Не все лишние Wiki-фрагменты удалось удалить")
        if result.matches == result.successful:
            return
        if not result.successful:
            raise WeaviateBaseError("Очистка Wiki-фрагментов не продвигается")
