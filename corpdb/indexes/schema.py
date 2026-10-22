import weaviate.classes.config as wvc

from corpdb.indexes.client import create_connection


def create_schema():
    with create_connection() as client:
        if not client.collections.exists("DocumentChunk"):
            client.collections.create(
                name="DocumentChunk",
                vector_config=wvc.Configure.Vectors.self_provided(
                    name="qwen",
                    vector_index_config=wvc.Configure.VectorIndex.hnsw(
                        distance_metric=wvc.VectorDistances.COSINE,
                    ),
                ),
                properties=[
                    wvc.Property(
                        name="document_id",
                        data_type=wvc.DataType.INT,
                        description="ID документа из PostgreSQL",
                    ),
                    wvc.Property(
                        name="index_run_id",
                        data_type=wvc.DataType.TEXT,
                        description="Метка набора фрагментов",
                        tokenization=wvc.Tokenization.FIELD,
                    ),
                    wvc.Property(
                        name="storage_key",
                        data_type=wvc.DataType.TEXT,
                        description="Ключ документа в MinIO",
                        tokenization=wvc.Tokenization.FIELD,
                    ),
                    wvc.Property(
                        name="position",
                        data_type=wvc.DataType.INT,
                        description="Порядковый номер фрагмента, начиная с 0",
                    ),
                    wvc.Property(
                        name="text",
                        data_type=wvc.DataType.TEXT,
                        description="Текст фрагмента",
                    ),
                    wvc.Property(
                        name="token_count",
                        data_type=wvc.DataType.INT,
                        description="Число токенов",
                    ),
                ],
            )


if __name__ == "__main__":
    create_schema()
