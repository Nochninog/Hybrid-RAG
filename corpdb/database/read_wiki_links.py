from corpdb.database.client import transaction_connection


def read_wiki_links(source_page_id: int) -> list[tuple[int, str, str]]:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    links.target_page_id,
                    pages.title,
                    links.explanation
                FROM wiki_page_links AS links
                JOIN wiki_pages AS pages
                    ON pages.id = links.target_page_id
                WHERE links.source_page_id = %s
                ORDER BY links.target_page_id
                """,
                (source_page_id,),
            )
            return cursor.fetchall()