FROM node:22-bookworm-slim
ENV PUPPETEER_SKIP_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    HOME=/tmp/sandbox-home \
    XDG_CACHE_HOME=/tmp/xdg-cache \
    NPM_CONFIG_CACHE=/tmp/npm-cache

RUN apt-get update && apt-get install -y --no-install-recommends chromium ffmpeg ca-certificates fonts-inter && rm -rf /var/lib/apt/lists/*
WORKDIR /sandbox
COPY . /sandbox/project
RUN npm ci --prefix /sandbox/project/compositions
RUN useradd --create-home --uid 10001 sandbox
USER sandbox
CMD ["sleep", "infinity"]
