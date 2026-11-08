"""Запись Wiki-страницы и её источников одной транзакцией."""

from corpdb.database.client import transaction_connection


def insert_wiki_page(title: str, content: str, document_ids: list[int]) -> int:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO wiki_pages (title, content) VALUES (%s, %s) RETURNING id",
                (title, content),
            )
            page_id = cursor.fetchone()[0]
            cursor.executemany(
                "INSERT INTO wiki_page_documents (wiki_page_id, document_id) VALUES (%s, %s)",
                [(page_id, document_id) for document_id in document_ids],
            )
    return page_id
