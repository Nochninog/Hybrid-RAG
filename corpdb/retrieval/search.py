"""Поиск фрагментов и объединение стартовых Wiki-страниц."""

import math

from corpdb.database.read_active_document_indexes import read_active_document_indexes
from corpdb.database.read_documents_for_wiki_pages import read_documents_for_wiki_pages
from corpdb.database.read_wiki_pages_for_documents import read_wiki_pages_for_documents
from corpdb.embeddings.qwen import embed_texts
from corpdb.indexes.client import create_connection
from corpdb.indexes.search_document_chunks import search_document_chunks
from corpdb.indexes.search_wiki_chunks import search_wiki_chunks


def search_question(question: str, *, limit: int = 10) -> dict:
    """Возвращает фрагменты документов и стартовые Wiki с основаниями поиска."""
    result, _ = search_question_with_vector(question, limit=limit)
    return result


def search_question_with_vector(question: str, *, limit: int) -> tuple[dict, list[float]]:
    """Возвращает результат Merge и вектор вопроса для следующего этапа."""
    question = question.strip()
    if not question:
        raise ValueError("Вопрос не должен быть пустым")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("Лимит поиска должен быть положительным целым числом")

    active_documents = read_active_document_indexes()
    vector, = embed_texts([question])
    with create_connection() as client:
        document_matches = search_document_chunks(
            vector, active_documents=active_documents, client=client, limit=limit,
        )
        wiki_matches = search_wiki_chunks(vector, client=client, limit=limit)

    document_chunks = [_chunk_evidence(match, "document_id") for match in document_matches]
    document_pages = read_wiki_pages_for_documents(list(dict.fromkeys(
        chunk["document_id"] for chunk in document_chunks
    )))

    grouped = {}
    for match in wiki_matches:
        chunk = _chunk_evidence(match, "wiki_page_id")
        grouped.setdefault(chunk["wiki_page_id"], []).append({"channel": "wiki", **chunk})
    for chunk in document_chunks:
        for page_id in document_pages.get(chunk["document_id"], []):
            grouped.setdefault(page_id, []).append({"channel": "document", **chunk})

    start_pages = []
    for page_id, evidence in grouped.items():
        evidence.sort(key=lambda item: (item["distance"], item["channel"], item["matched_chunk_uuid"]))
        start_pages.append({
            "page_id": page_id,
            "best_distance": evidence[0]["distance"],
            "channels": sorted({item["channel"] for item in evidence}),
            "evidence": evidence,
        })
    start_pages.sort(key=lambda page: (page["best_distance"], page["page_id"]))
    return {"document_chunks": document_chunks, "start_pages": start_pages}, vector


def select_document_chunks(page_ids: list[int], vector: list[float], *, limit: int) -> list[dict]:
    """Ищет по актуальным фрагментам только связанных с Wiki оригиналов."""
    documents = read_documents_for_wiki_pages(page_ids)
    if not documents:
        return []
    active_documents = [row for row in read_active_document_indexes() if row[0] in documents]
    if not active_documents:
        return []
    with create_connection() as client:
        matches = search_document_chunks(
            vector, active_documents=active_documents, client=client, limit=limit,
        )
    return [
        {**_chunk_evidence(match, "document_id"), "wiki_page_ids": documents[match.properties["document_id"]]}
        for match in matches
    ]


def _chunk_evidence(match, id_property: str) -> dict:
    distance = match.metadata.distance
    if distance is None or not math.isfinite(distance):
        raise ValueError(f"Совпадение {match.uuid} не имеет корректного расстояния")
    return {
        id_property: match.properties[id_property],
        "matched_chunk_uuid": str(match.uuid),
        "matched_position": match.properties["position"],
        "text": match.properties["text"],
        "distance": distance,
    }
