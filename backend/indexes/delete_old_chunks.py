"""Удаление фрагментов прежних оригиналов и заменённого активного набора."""

from uuid import UUID

from weaviate.classes.query import Filter
from weaviate.exceptions import WeaviateBaseError

from backend.indexes.client import create_connection


def delete_old_chunks(
    document_id: int,
    storage_key: str,
    active_run_id: UUID,
    previous_run_id: UUID | None,
) -> None:
    obsolete = Filter.by_property("storage_key").not_equal(storage_key)
    if previous_run_id is not None:
        obsolete = obsolete | Filter.by_property("index_run_id").equal(str(previous_run_id))
    where = (
        Filter.by_property("document_id").equal(document_id)
        & Filter.by_property("index_run_id").not_equal(str(active_run_id))
        & obsolete
    )
    with create_connection() as client:
        collection = client.collections.use("DocumentChunk")
        while True:
            result = collection.data.delete_many(where=where)
            if result.failed:
                raise WeaviateBaseError("Не все прежние фрагменты удалось удалить")
            if result.matches == result.successful:
                return
            if not result.successful:
                raise WeaviateBaseError("Очистка прежних фрагментов не продвигается")
