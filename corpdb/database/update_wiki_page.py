"""Замена текста существующей Wiki с проверкой прочитанной версии."""
from corpdb.database.errors import DatabaseError


def update_wiki_page_content(page_id, title, expected_content, content, document_ids, *, connection):
    """Использует транзакцию вызывающего кода; ID, название и источники сохраняются."""
    if not content.strip():
        raise ValueError('Нельзя сохранить пустую Wiki-страницу')
    with connection.cursor() as cursor:
        cursor.execute('SELECT title, content FROM wiki_pages WHERE id=%s FOR UPDATE', (page_id,))
        if cursor.fetchone() != (title, expected_content):
            raise DatabaseError(f'Wiki {page_id} изменилась после подготовки обновления')
        cursor.execute('SELECT document_id FROM wiki_page_documents WHERE wiki_page_id=%s ORDER BY document_id', (page_id,))
        if [row[0] for row in cursor.fetchall()] != sorted(set(document_ids)):
            raise DatabaseError(f'Источники Wiki {page_id} изменились после подготовки обновления')
        cursor.execute('UPDATE wiki_pages SET content=%s WHERE id=%s', (content, page_id))
