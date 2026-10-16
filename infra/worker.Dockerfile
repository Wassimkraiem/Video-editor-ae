# Node 22 for `npx hyperframes` and the Claude Code runtime used by the SDK.
FROM node:22-bookworm-slim AS node

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# ffmpeg for ingest/verification, Chromium + fonts for HyperFrames renders.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg chromium fonts-inter fonts-noto-core ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY services ./services
COPY packages ./packages
COPY skills ./skills
COPY compositions ./compositions
RUN pip install --no-cache-dir -e '.[api,agent,media,skills]'
RUN useradd --create-home --uid 10001 app \
    && mkdir -p /work/storage /work/projects /home/app/.claude \
    && chown -R app:app /app /work /home/app/.claude
USER app
CMD ["python", "-m", "services.worker"]
