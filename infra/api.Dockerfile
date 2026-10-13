FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md alembic.ini ./
COPY services ./services
COPY packages ./packages
# The API seeds the skill catalog and installs skills into new projects.
COPY skills ./skills
RUN pip install --no-cache-dir -e '.[api]'
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /work/storage /work/projects \
    && chown -R app:app /app /work
USER app
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn services.api.main:app --host 0.0.0.0 --port 8000"]
