"""Подбор Wiki-кандидатов по векторам фрагментов исходной страницы."""

import math

from backend.database.read_wiki_page import read_wiki_page
from backend.database.read_active_document_indexes import read_active_document_indexes
from backend.database.read_wiki_pages_for_documents import read_wiki_pages_for_documents
from backend.indexes.client import create_connection
from backend.indexes.read_wiki_chunks import read_wiki_chunks
from backend.indexes.search_wiki_chunks import search_wiki_chunks
from backend.indexes.search_document_chunks import search_document_chunks


def find_wiki_candidates(
    page_id: int,
    *,
    hits_per_chunk: int = 10,
    max_candidates: int = 20,
    evidence_per_candidate: int = 2,
) -> dict:
    """Два канала кандидатов; evidence_per_candidate применяется к каждому каналу."""
    for name, value in (
        ("hits_per_chunk", hits_per_chunk),
        ("max_candidates", max_candidates),
        ("evidence_per_candidate", evidence_per_candidate),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"{name} должен быть положительным целым числом")

    # Отсутствующая страница и отсутствие её индекса — разные ошибки.
    read_wiki_page(page_id)
    grouped = {}
    match_count = 0
    document_match_count = 0
    document_evidence = {}

    def remember(target_id, evidence):
        if target_id == page_id:
            return
        by_chunk = grouped.setdefault(target_id, {})
        key = (evidence["channel"], evidence["matched_chunk_uuid"])
        previous = by_chunk.get(key)
        if previous is None or evidence["distance"] < previous["distance"]:
            by_chunk[key] = evidence

    with create_connection() as client:
        chunks = read_wiki_chunks(page_id, client=client)
        if not chunks:
            raise ValueError(f"Wiki {page_id} не имеет фрагментов. Сначала проиндексируйте страницу")

        active_documents = read_active_document_indexes()

        for chunk in chunks:
            vector = chunk.vector.get("qwen")
            if not vector or not all(math.isfinite(value) for value in vector):
                raise ValueError(f"Фрагмент {chunk.uuid} не имеет корректного вектора qwen")
            matches = search_wiki_chunks(
                vector, exclude_page_id=page_id, client=client, limit=hits_per_chunk,
            )
            match_count += len(matches)
            document_matches = search_document_chunks(
                vector, active_documents=active_documents, client=client, limit=hits_per_chunk,
            ) if active_documents else []
            document_match_count += len(document_matches)
            for channel, match in (
                [("wiki", match) for match in matches]
                + [("document", match) for match in document_matches]
            ):
                distance = match.metadata.distance
                if distance is None or not math.isfinite(distance):
                    raise ValueError(f"Совпадение {match.uuid} не имеет корректного расстояния")
                evidence = {
                    "channel": channel,
                    "source_chunk_uuid": str(chunk.uuid),
                    "source_position": chunk.properties["position"],
                    "source_text": chunk.properties["text"],
                    "matched_chunk_uuid": str(match.uuid),
                    "matched_position": match.properties["position"],
                    "text": match.properties["text"],
                    "distance": distance,
                }
                if channel == "wiki":
                    remember(match.properties["wiki_page_id"], evidence)
                else:
                    evidence.update(
                        document_id=match.properties["document_id"],
                        storage_key=match.properties["storage_key"],
                        index_run_id=match.properties["index_run_id"],
                    )
                    previous = document_evidence.get(str(match.uuid))
                    if previous is None or distance < previous["distance"]:
                        document_evidence[str(match.uuid)] = evidence

    # Один пакетный запрос для всех найденных документов; один документ может
    # вести к нескольким Wiki, а документ без Wiki не создаёт кандидата.
    document_pages = read_wiki_pages_for_documents(sorted({
        item["document_id"] for item in document_evidence.values()
    }))
    for evidence in document_evidence.values():
        for target_id in document_pages.get(evidence["document_id"], []):
            remember(target_id, evidence)

    ranked = sorted(grouped, key=lambda target_id: (
        min(item["distance"] for item in grouped[target_id].values()), target_id,
    ))
    candidates = []
    for target_id in ranked[:max_candidates]:
        title, _ = read_wiki_page(target_id)
        all_evidence = list(grouped[target_id].values())
        channels = [channel for channel in ("wiki", "document")
                    if any(item["channel"] == channel for item in all_evidence)]
        evidence = []
        for channel in channels:
            evidence.extend(sorted(
                (item for item in all_evidence if item["channel"] == channel),
                key=lambda item: (item["distance"], item["matched_position"], item["matched_chunk_uuid"]),
            )[:evidence_per_candidate])
        evidence.sort(key=lambda item: (item["distance"], item["channel"], item["matched_chunk_uuid"]))
        candidates.append({
            "page_id": target_id,
            "title": title,
            "best_distance": evidence[0]["distance"],
            "channels": channels,
            "evidence": evidence,
        })

    return {
        "source_page_id": page_id,
        "candidates": candidates,
        "limits": {
            "hits_per_chunk": hits_per_chunk,
            "max_candidates": max_candidates,
            "evidence_per_candidate": evidence_per_candidate,
        },
        "stats": {
            "source_chunk_count": len(chunks),
            "search_count": len(chunks) * (2 if active_documents else 1),
            "wiki_search_count": len(chunks),
            "document_search_count": len(chunks) if active_documents else 0,
            "match_count": match_count + document_match_count,
            "wiki_match_count": match_count,
            "document_match_count": document_match_count,
            "unique_candidate_count": len(grouped),
            "returned_candidate_count": len(candidates),
        },
        "truncated": len(ranked) > max_candidates,
    }
