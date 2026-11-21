import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import URL, create_engine
from sqlalchemy.pool import NullPool


project_root = Path(__file__).resolve().parents[3]
load_dotenv(project_root / ".env")

database_url = URL.create(
    drivername="postgresql+psycopg",
    username=os.environ["POSTGRES_USER"],
    password=os.environ["POSTGRES_PASSWORD"],
    host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
    port=int(os.getenv("POSTGRES_PORT", "5432")),
    database=os.environ["POSTGRES_DB"],
)

engine = create_engine(database_url, poolclass=NullPool)

try:
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=None,
        )

        with context.begin_transaction():
            context.run_migrations()
finally:
    engine.dispose()
