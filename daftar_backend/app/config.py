import os


class Config:
    # SQLite file lives next to the package by default; override via env var for tests
    # or deployment (e.g. a persistent volume path in production).
    DATABASE_PATH = os.environ.get(
        "DAFTAR_DB_PATH",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "daftar.sqlite3"),
    )
    JWT_SECRET = os.environ.get("DAFTAR_JWT_SECRET", "dev-secret-change-me-in-production")
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRES_DAYS = int(os.environ.get("DAFTAR_JWT_EXPIRES_DAYS", "7"))
    JSON_AS_ASCII = False  # keep Persian text un-escaped in JSON responses
