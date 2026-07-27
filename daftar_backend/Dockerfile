FROM python:3.12-slim

WORKDIR /app

# System deps: none needed beyond what python:slim ships with (sqlite3 is built into
# Python's stdlib, no separate package required).

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY frontend ./frontend
COPY run.py .

# The SQLite file lives here. docker-compose.yml mounts a named volume onto this exact
# path so the database survives image rebuilds/container recreation.
ENV DAFTAR_DB_PATH=/data/daftar.sqlite3
RUN mkdir -p /data

EXPOSE 5000

# A single worker on purpose: SQLite tolerates concurrent connections fine (WAL mode is
# enabled in app/db.py), but a single worker keeps writes strictly serialized and avoids
# ever having to think about cross-process locking for what is a small personal-scale app.
# Bump --workers if this ever moves to a real multi-user database instead of SQLite.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "run:app"]
