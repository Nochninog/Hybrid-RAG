"""Чтение всех фрагментов Wiki вместе с сохранёнными векторами."""

from weaviate.classes.query import Filter, Sort

def read_wiki_chunks(wiki_page_id: int, *, client):
    collection = client.collections.get("WikiChunk")

    filters = Filter.by_property("wiki_page_id").equal(wiki_page_id)
    chunks = []
    offset = 0

    while True:
        result = collection.query.fetch_objects(
            filters=filters,
            include_vector=True,
            limit=100,
            offset=offset,
            sort=Sort.by_property("position", ascending=True),
        )
        if not result.objects:
            break

        chunks.extend(result.objects)
        offset += len(result.objects)

    return sorted(chunks, key=lambda chunk: chunk.properties["position"])
