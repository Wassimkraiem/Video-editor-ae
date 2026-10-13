FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml README.md ./
COPY services ./services
COPY packages ./packages
COPY skills ./skills
COPY compositions ./compositions
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg ca-certificates && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -e '.[api,agent,media]'
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /work/storage /work/projects \
    && chown -R app:app /app /work
USER app
CMD ["python", "-m", "services.worker"]
