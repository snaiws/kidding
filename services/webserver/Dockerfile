FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# 프로젝트 루트의 파일들 복사
COPY uv.lock pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

FROM python:3.12-slim-bookworm

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash app

WORKDIR /app

# .venv 복사 (uv 스테이지에서)
COPY --from=uv --chown=app:app /app/.venv /app/.venv

# 프로젝트 파일들 복사 (빌드 컨텍스트는 webservice/ 디렉토리)
COPY --chown=app:app src/ /app/src/
COPY --chown=app:app . /app/

USER app

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]