FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --gid 10001 app

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

USER 10001:10001

CMD ["python", "-m", "link_checker.bot"]

FROM runtime AS test

USER root
COPY tests ./tests
COPY scripts ./scripts
RUN pip install --no-cache-dir ".[dev]"
ENV RUFF_CACHE_DIR=/tmp/ruff-cache \
    MYPY_CACHE_DIR=/tmp/mypy-cache
USER 10001:10001
