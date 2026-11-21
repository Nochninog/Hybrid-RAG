"""Поиск фрагментов и объединение стартовых Wiki-страниц."""

import math

from backend.database.read_active_document_indexes import read_active_document_indexes
from backend.database.read_documents_for_wiki_pages import read_documents_for_wiki_pages
from backend.database.read_wiki_pages_for_documents import read_wiki_pages_for_documents
from backend.embeddings.qwen import embed_texts
from backend.indexes.client import create_connection
from backend.indexes.search_document_chunks import search_document_chunks
from backend.indexes.search_wiki_chunks import search_wiki_chunks


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


def find_document_candidates(
    page_ids: list[int], vector: list[float], search_queries: dict[int, str],
    *, initial_chunks: list[dict] | None = None,
    per_page_limit: int = 10,
) -> list[dict]:
    """Объединяет исходные фрагменты с ограниченной выдачей по каждой Wiki."""
    if type(per_page_limit) is not int or per_page_limit <= 0:
        raise ValueError("per_page_limit должен быть положительным целым числом")
    documents = read_documents_for_wiki_pages(page_ids)
    active_documents = read_active_document_indexes()
    active_states = set(active_documents)
    candidates = {}
    for chunk in initial_chunks or []:
        state = (chunk["document_id"], chunk["storage_key"], chunk["index_run_id"])
        if state in active_states:
            candidates.setdefault(chunk["matched_chunk_uuid"], {
                **chunk, "wiki_page_ids": documents.get(chunk["document_id"], []),
                "retrieval_origins": ["initial_search"],
            })
    active_by_page = {}
    for row in active_documents:
        for page_id in documents.get(row[0], []):
            active_by_page.setdefault(page_id, []).append(row)
    if not active_by_page:
        return list(candidates.values())

    queries = list(dict.fromkeys(
        search_queries[page_id] for page_id in active_by_page if page_id in search_queries
    ))
    vectors = dict(zip(queries, embed_texts(queries), strict=True)) if queries else {}
    with create_connection() as client:
        for page_id in page_ids:
            matches = search_document_chunks(
                vectors.get(search_queries.get(page_id), vector),
                active_documents=active_by_page.get(page_id, []), client=client, limit=per_page_limit,
            )
            for match in matches:
                chunk = _chunk_evidence(match, "document_id")
                chunk["wiki_page_ids"] = documents[chunk["document_id"]]
                chunk["retrieval_origins"] = ["wiki_search"]
                saved = candidates.setdefault(chunk["matched_chunk_uuid"], chunk)
                if "wiki_search" not in saved["retrieval_origins"]:
                    saved["retrieval_origins"].append("wiki_search")
    return list(candidates.values())


def _chunk_evidence(match, id_property: str) -> dict:
    distance = match.metadata.distance
    if distance is None or not math.isfinite(distance):
        raise ValueError(f"Совпадение {match.uuid} не имеет корректного расстояния")
    chunk = {
        id_property: match.properties[id_property],
        "matched_chunk_uuid": str(match.uuid),
        "matched_position": match.properties["position"],
        "text": match.properties["text"],
        "distance": distance,
    }
    if id_property == "document_id":
        chunk.update(storage_key=match.properties["storage_key"],
                     index_run_id=str(match.properties["index_run_id"]))
    return chunk
