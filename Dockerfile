FROM python:3.12-slim AS build
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN uv pip install --system --no-cache .

FROM python:3.12-slim
RUN useradd -m -u 1000 bot && apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin/plex-tg-bot /usr/local/bin/plex-tg-bot
COPY src /app/src
USER bot
ENV PYTHONUNBUFFERED=1
EXPOSE 9095
HEALTHCHECK --interval=30s --timeout=5s --retries=5 \
  CMD curl -fsS http://localhost:9095/healthz || exit 1
ENTRYPOINT ["plex-tg-bot"]
