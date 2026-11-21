from backend.database.client import transaction_connection
from backend.database.errors import DatabaseError


def read_document_filename(document_id: int) -> str:
    """Возвращает исходное имя файла для выбора способа извлечения текста."""
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT filename FROM documents WHERE id = %s", (document_id,))
            result = cursor.fetchone()
            if result is None:
                raise DatabaseError(f"Документ с id={document_id} не найден.")
            return result[0]


def read_document(
    document_id
):
    
    with transaction_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT storage_bucket, storage_key
                FROM documents 
                WHERE id = %s
                """,
                (document_id,),
            )
            result = cursor.fetchone()
            if result is None:
                raise DatabaseError(f"Документ с id={document_id} не найден.")
            return result
        
