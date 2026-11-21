# Поиск по корпоративной базе знаний

Система помогает находить ответы в корпоративных документах. В веб-интерфейсе можно загрузить PDF, TXT или Markdown, собрать из документов Wiki-страницы и задать вопрос. В ответе система указывает документы, на которые опиралась.

## Архитектура

- **Веб-интерфейс** на React. Nginx раздаёт страницы и передаёт запросы двум сервисам FastAPI.
- **`knowledge-service`** загружает и индексирует документы, создаёт Wiki-страницы и связи между ними.
- **`search-service`** отвечает на вопросы по базе знаний и возвращает ссылки на источники.
- **Хранилища.** MinIO хранит оригиналы, PostgreSQL — метаданные, Wiki и связи, Weaviate — поисковые индексы. Векторы строит Qwen через Cloud.ru.

## Как работает поиск

Алгоритм поиска разработан в рамках дипломной работы. Система ищет фрагменты документов и Wiki-страниц, объединяет результаты в набор стартовых страниц и с помощью языковой модели обходит связи между ними. Затем она отбирает подходящие документы и формирует ответ со ссылками на источники.

## Как запустить

1. Установите Docker с Compose. Создайте в корне проекта файл `.env` и заполните его по [таблице переменных окружения](#переменные-окружения).
2. Из корня проекта запустите весь стек:

   ```sh
   docker compose up -d --build web
   ```

3. Если хранилища пустые, после запуска один раз примените миграции, создайте поисковые коллекции и бакет для оригиналов:

   ```sh
   docker compose exec knowledge-service python -m alembic upgrade head
   docker compose exec knowledge-service python -m backend.indexes.schema
   docker compose exec knowledge-service python -m backend.indexes.wiki_schema
   docker compose exec knowledge-service python -c "from backend.storage.client import create_client; create_client().create_bucket(Bucket='corpdb-originals')"
   ```

4. Откройте [веб-интерфейс](http://127.0.0.1:8088).

## Переменные окружения

Для TLS поместите корневой сертификат в `data/certs/russian_trusted_root_ca_pem.crt` или задайте свой путь внутри контейнера.

| Переменная в `.env` | Что указать |
| --- | --- |
| `POSTGRES_USER` | Имя пользователя PostgreSQL |
| `POSTGRES_PASSWORD` | Пароль PostgreSQL |
| `POSTGRES_DB` | Имя базы PostgreSQL |
| `MINIO_USERNAME` | Имя пользователя MinIO |
| `MINIO_PASSWORD` | Пароль MinIO |
| `CLOUD_RU_API_KEY` | Ключ API для построения векторов |
| `GIGACHAT_CREDENTIALS` | Ключ авторизации для языковой модели |
| `GIGACHAT_SCOPE` | Необязательно. Область доступа к API, по умолчанию `GIGACHAT_API_PERS` |
| `CORPDB_GIGACHAT_CA_BUNDLE` | Необязательно. Путь к сертификату внутри контейнера, по умолчанию `/certs/russian_trusted_root_ca_pem.crt` |
