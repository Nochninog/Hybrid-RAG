"""Поиск похожих Wiki-фрагментов по готовому вектору Qwen."""

from weaviate.classes.query import Filter, MetadataQuery


def search_wiki_chunks(
    vector: list[float],
    *,
    exclude_page_id: int | None = None,
    client,
    limit: int = 10,
):
    """Возвращает объекты с metadata.distance и необязательным исключением страницы."""
    if limit <= 0:
        raise ValueError("Лимит поиска должен быть положительным")

    collection = client.collections.get("WikiChunk")
    filters = None
    if exclude_page_id is not None:
        filters = Filter.by_property("wiki_page_id").not_equal(exclude_page_id)
    result = collection.query.near_vector(
        near_vector=vector,
        target_vector="qwen",
        filters=filters,
        limit=limit,
        include_vector=False,
        return_metadata=MetadataQuery(distance=True),
    )
    return result.objects
