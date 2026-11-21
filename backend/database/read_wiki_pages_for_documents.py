"""Wiki-страницы, связанные с выбранными документами-источниками."""

from backend.database.client import transaction_connection


def read_wiki_pages_for_documents(document_ids: list[int]) -> dict[int, list[int]]:
    if not document_ids:
        return {}
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT document_id, wiki_page_id FROM wiki_page_documents "
                "WHERE document_id = ANY(%s) ORDER BY document_id, wiki_page_id",
                (list(dict.fromkeys(document_ids)),),
            )
            pages = {}
            for document_id, page_id in cursor.fetchall():
                pages.setdefault(document_id, []).append(page_id)
            return pages
