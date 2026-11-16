# One image for every workload: ingestion jobs, dbt transform, webhook receiver, MCP server.
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DBT_PROJECT_DIR=/app/transform \
    DBT_PROFILES_DIR=/app/transform \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install ".[transform,agents]"

COPY transform ./transform

RUN useradd --uid 10001 --create-home app && chown -R app:app /app
USER app

ENTRYPOINT ["hospitality-elt"]
CMD ["daily"]
