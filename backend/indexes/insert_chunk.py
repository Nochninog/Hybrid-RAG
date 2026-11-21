"""Запись одного фрагмента с готовым вектором в Weaviate."""

from contextlib import nullcontext
from uuid import NAMESPACE_URL, UUID, uuid5

from weaviate import WeaviateClient

from backend.indexes.client import create_connection
from backend.ingestion.models import DocumentChunk


def insert_chunk(
    chunk: DocumentChunk,
    storage_key: str,
    index_run_id: UUID,
    vector: list[float],
    *,
    client: WeaviateClient | None = None,
) -> UUID:
    chunk_id = uuid5(
        NAMESPACE_URL, f"corpdb:document-chunk:{index_run_id}:{chunk.position}"
    )
    with (nullcontext(client) if client is not None else create_connection()) as client:
        collection = client.collections.use("DocumentChunk")
        return collection.data.insert(
            uuid=chunk_id,
            properties={
                "document_id": chunk.document_id,
                "index_run_id": str(index_run_id),
                "storage_key": storage_key,
                "position": chunk.position,
                "text": chunk.text,
                "token_count": chunk.token_count,
            },
            vector={"qwen": vector},
        )
