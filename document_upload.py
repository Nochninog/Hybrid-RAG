"""Совместимость с прежним запуском: python document_upload.py <файл>."""

from corpdb.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
