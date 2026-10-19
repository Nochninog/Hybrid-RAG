class DatabaseError(Exception):
    pass


class DatabaseWriteError(DatabaseError):
    """Запись завершилась ошибкой до попытки commit."""
