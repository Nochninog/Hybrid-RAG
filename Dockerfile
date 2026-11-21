FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HF_HOME=/home/app/.cache/huggingface
WORKDIR /app
COPY requirements.txt requirements-api.txt ./
RUN pip install --no-cache-dir -r requirements-api.txt \
    && useradd --create-home app
COPY alembic.ini ./
COPY corpdb ./corpdb
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

FROM runtime AS knowledge
CMD ["python", "-m", "uvicorn", "corpdb.api.knowledge:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS search
CMD ["python", "-m", "uvicorn", "corpdb.api.search:app", "--host", "0.0.0.0", "--port", "8000"]
