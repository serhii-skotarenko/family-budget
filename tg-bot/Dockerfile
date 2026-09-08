FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_PATH=/data/budget.sqlite3

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic ./alembic
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# SQLite must live on a persistent volume — a redeploy wipes the container FS.
# Deliberately no `VOLUME ["/data"]`: Railway's builder rejects the directive
# outright ("docker VOLUME ... is not supported, use Railway Volumes"). The
# mount is declared by the platform instead — a Railway volume at /data, and
# `budget-data:/data` in docker-compose.yml for local runs.

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["python", "-m", "budget_bot"]
