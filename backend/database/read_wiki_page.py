"""Чтение сохранённой Wiki-страницы."""

from backend.database.client import transaction_connection
from backend.database.errors import DatabaseError


def read_wiki_page(wiki_page_id: int) -> tuple[str, str]:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT title, content FROM wiki_pages WHERE id = %s", (wiki_page_id,))
            result = cursor.fetchone()
            if result is None:
                raise DatabaseError(f"Wiki-страница с id={wiki_page_id} не найдена")
            return result
