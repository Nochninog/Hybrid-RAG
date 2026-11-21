"""Сохранение направленной связи между Wiki-страницами."""

from backend.database.client import transaction_connection


def insert_wiki_link(source_page_id: int, target_page_id: int, explanation: str) -> None:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO wiki_page_links (
                    source_page_id,
                    target_page_id,
                    explanation
                )
                VALUES (%s, %s, %s)
                ON CONFLICT (source_page_id, target_page_id)
                DO UPDATE SET explanation = EXCLUDED.explanation
                """,
                (source_page_id, target_page_id, explanation),
            )
            
