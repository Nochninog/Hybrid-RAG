"""Общий HTTP-контракт ошибок без раскрытия настроек и ответов провайдеров."""

import logging
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)


class BodyLimitMiddleware:
    """Ограничивает поток до multipart-разбора, включая chunked-загрузки."""

    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        size = 0

        async def limited_receive():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > self.max_bytes:
                raise HTTPException(413, "Превышен допустимый размер запроса")
            return message

        headers = dict(scope.get("headers", []))
        try:
            declared = int(headers.get(b"content-length", b"0"))
        except ValueError:
            response = JSONResponse({"detail": "Некорректный Content-Length"}, status_code=400)
            return await response(scope, receive, send)
        if declared > self.max_bytes:
            response = JSONResponse({"detail": "Превышен допустимый размер запроса"}, status_code=413)
            return await response(scope, receive, send)
        await self.app(scope, limited_receive, send)


def create_app(service: str) -> FastAPI:
    app = FastAPI(title=f"CorpDB {service}", version="0.1.0")

    @app.get("/health")
    def health():
        # Liveness: не вызывает хранилища, токенизатор или платные API.
        return {"status": "ok", "service": service}

    return app


@contextmanager
def operation(stage: str, **state):
    """Передаёт стадию и уже сохранённые ID при частичном выполнении."""
    try:
        yield
    except HTTPException:
        raise
    except Exception as exc:
        # Не выводим str(exc): ошибка внешнего клиента может содержать секреты.
        logger.error("Operation %s failed (%s)", stage, type(exc).__name__)
        raise HTTPException(status_code=502, detail={
            "stage": stage,
            "message": "Операция не завершена. Проверьте состояние перед повтором.",
            **state,
        }) from exc
