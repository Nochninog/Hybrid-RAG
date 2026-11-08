"""Отдельная коллекция для фрагментов Wiki с векторами Qwen."""

import weaviate.classes.config as wvc

from corpdb.indexes.client import create_connection


def create_wiki_schema() -> None:
    with create_connection() as client:
        if not client.collections.exists("WikiChunk"):
            client.collections.create(
                name="WikiChunk",
                vector_config=wvc.Configure.Vectors.self_provided(
                    name="qwen",
                    vector_index_config=wvc.Configure.VectorIndex.hnsw(
                        distance_metric=wvc.VectorDistances.COSINE,
                    ),
                ),
                properties=[
                    wvc.Property(name="wiki_page_id", data_type=wvc.DataType.INT),
                    wvc.Property(name="position", data_type=wvc.DataType.INT),
                    wvc.Property(name="title", data_type=wvc.DataType.TEXT),
                    wvc.Property(name="headings", data_type=wvc.DataType.TEXT_ARRAY),
                    wvc.Property(name="text", data_type=wvc.DataType.TEXT),
                    wvc.Property(name="token_count", data_type=wvc.DataType.INT),
                ],
            )


if __name__ == "__main__":
    create_wiki_schema()
