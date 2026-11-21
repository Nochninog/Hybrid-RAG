"""Чтение каталогов для веб-интерфейса без изменения документов и Wiki."""

from backend.database.client import transaction_connection


def list_documents(query: str = "", limit: int = 30, offset: int = 0) -> dict:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            # strpos ищет буквальную подстроку, а не шаблон LIKE из пользовательского ввода.
            cursor.execute("SELECT count(*) FROM documents WHERE strpos(lower(filename), lower(%s)) > 0",
                           (query,))
            total = cursor.fetchone()[0]
            cursor.execute(
                "SELECT d.id, d.filename, d.size_bytes, d.active_index_run_id IS NOT NULL, "
                "ARRAY(SELECT w.wiki_page_id FROM wiki_page_documents w "
                "WHERE w.document_id = d.id ORDER BY w.wiki_page_id) "
                "FROM documents d WHERE strpos(lower(d.filename), lower(%s)) > 0 "
                "ORDER BY d.id DESC LIMIT %s OFFSET %s", (query, limit, offset))
            items = [dict(zip(("id", "filename", "size_bytes", "indexed", "wiki_page_ids"), row))
                     for row in cursor.fetchall()]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def read_document_details(document_id: int) -> dict | None:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, filename, size_bytes, active_index_run_id IS NOT NULL "
                           "FROM documents WHERE id = %s", (document_id,))
            row = cursor.fetchone()
    return dict(zip(("id", "filename", "size_bytes", "indexed"), row)) if row else None


def list_wiki_pages(query: str = "", limit: int = 30, offset: int = 0) -> dict:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM wiki_pages WHERE strpos(lower(title), lower(%s)) > 0",
                           (query,))
            total = cursor.fetchone()[0]
            cursor.execute(
                "SELECT p.id, p.title, "
                "ARRAY(SELECT w.document_id FROM wiki_page_documents w "
                "WHERE w.wiki_page_id = p.id ORDER BY w.document_id), "
                "(SELECT count(*) FROM wiki_page_links l WHERE l.source_page_id = p.id) "
                "FROM wiki_pages p WHERE strpos(lower(p.title), lower(%s)) > 0 "
                "ORDER BY p.id DESC LIMIT %s OFFSET %s", (query, limit, offset))
            items = [dict(zip(("id", "title", "document_ids", "link_count"), row))
                     for row in cursor.fetchall()]
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def read_wiki_details(page_id: int) -> dict | None:
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT p.id, p.title, p.content, "
                "ARRAY(SELECT w.document_id FROM wiki_page_documents w "
                "WHERE w.wiki_page_id = p.id ORDER BY w.document_id) "
                "FROM wiki_pages p WHERE p.id = %s", (page_id,))
            row = cursor.fetchone()
    return dict(zip(("id", "title", "content", "document_ids"), row)) if row else None
