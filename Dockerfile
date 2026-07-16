FROM python:3.12-slim

WORKDIR /app

# Copy both files so requirements.txt can resolve its pinned lock file while
# preserving the dependency layer cache between source-only changes.
COPY backend/requirements.txt backend/requirements.lock ./backend/
RUN python -m pip install --no-cache-dir -r backend/requirements.txt

COPY . .

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# MIGRATION_DATABASE_URL is supplied by the deployment environment and must
# point at Neon directly. A failed migration prevents an app process from
# serving against an unknown schema.
CMD ["sh", "-c", "python -m alembic -c backend/alembic.ini upgrade head && exec uvicorn backend.app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\""]
