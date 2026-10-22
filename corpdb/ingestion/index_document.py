"""Обработка и запись набора фрагментов сохранённого документа."""

from uuid import UUID, uuid4

from corpdb.database.activate_document_index import activate_document_index
from corpdb.database.read_document import read_document
from corpdb.embeddings.qwen import embed_texts
from corpdb.indexes.client import create_connection
from corpdb.indexes.insert_chunk import insert_chunk
from corpdb.ingestion.cleanup_document_index import cleanup_document_index
from corpdb.ingestion.operations import process_document


def index_document(document_id: int, extension: str) -> UUID:
    storage_location = read_document(document_id)
    chunks = process_document(document_id, extension)
    if read_document(document_id) != storage_location:
        raise ValueError("Документ заменён во время обработки; повторите индексацию")

    index_run_id = uuid4()
    if not chunks:
        previous_run_id = activate_document_index(document_id, *storage_location, index_run_id)
        cleanup_document_index(document_id, index_run_id, previous_run_id)
        return index_run_id

    vectors = embed_texts([chunk.text for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValueError("Число векторов не совпадает с числом фрагментов")

    with create_connection() as client:
        for chunk, vector in zip(chunks, vectors):
            insert_chunk(
                chunk, storage_location[1], index_run_id, vector, client=client
            )
    previous_run_id = activate_document_index(document_id, *storage_location, index_run_id)
    cleanup_document_index(document_id, index_run_id, previous_run_id)
    return index_run_id
