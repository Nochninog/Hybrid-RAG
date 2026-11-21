"""Документы-источники, связанные с найденными Wiki."""

from backend.database.client import transaction_connection


def read_documents_for_wiki_pages(page_ids: list[int]) -> dict[int, list[int]]:
    if not page_ids:
        return {}
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT document_id, wiki_page_id FROM wiki_page_documents "
                "WHERE wiki_page_id = ANY(%s) ORDER BY document_id, wiki_page_id",
                (page_ids,),
            )
            documents = {}
            for document_id, page_id in cursor.fetchall():
                documents.setdefault(document_id, []).append(page_id)
            return documents
