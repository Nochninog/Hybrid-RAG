"""Поиск только по активным наборам текущих оригиналов документов."""

from weaviate.classes.query import Filter, MetadataQuery


def search_document_chunks(
    vector: list[float],
    *,
    active_documents: list[tuple[int, str, str]],
    client,
    limit: int = 10,
):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("Лимит поиска должен быть положительным целым числом")
    if not active_documents:
        return []

    # Каждая тройка должна совпасть целиком; фильтруем до отбора top-k.
    filters = Filter.any_of([
        Filter.by_property("document_id").equal(document_id)
        & Filter.by_property("storage_key").equal(storage_key)
        & Filter.by_property("index_run_id").equal(str(index_run_id))
        for document_id, storage_key, index_run_id in active_documents
    ])
    result = client.collections.get("DocumentChunk").query.near_vector(
        near_vector=vector,
        target_vector="qwen",
        filters=filters,
        limit=limit,
        include_vector=False,
        return_metadata=MetadataQuery(distance=True),
    )
    return result.objects
