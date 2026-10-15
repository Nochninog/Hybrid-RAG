class DatabaseError(Exception):
    pass


class DatabaseWriteError(DatabaseError):
    """Запись завершилась ошибкой до подтверждения транзакции."""


class DatabaseCommitUnknownError(DatabaseError):
    """Не удалось подтвердить результат завершения транзакции."""