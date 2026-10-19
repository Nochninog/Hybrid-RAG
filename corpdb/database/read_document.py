from corpdb.database.client import transaction_connection
from corpdb.database.errors import DatabaseError


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
        
