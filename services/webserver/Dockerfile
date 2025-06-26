FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# 프로젝트 루트의 파일들 복사
COPY uv.lock pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# Proto 컴파일 스테이지
FROM uv AS proto-builder

# protoc 설치
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# proto 컴파일을 위한 grpcio-tools 설치
RUN --mount=type=cache,target=/root/.cache/uv \
    uv add grpcio-tools --no-sync

# proto 파일 복사 및 컴파일 (현재 webserver의 proto 폴더 사용)
COPY proto/ ./proto/
RUN mkdir -p . && \
    echo "Proto 파일 확인:" && ls -la ./proto/ && \
    echo "Proto 컴파일 시작..." && \
    uv run python -m grpc_tools.protoc \
        --python_out=. \
        --grpc_python_out=. \
        --proto_path=./proto \
        ./proto/audio_service.proto && \
    echo "Proto 컴파일 완료" && \
    ls -la ./audio_service_pb2*

FROM python:3.12-slim-bookworm

# 메타데이터
LABEL maintainer="your-team@company.com"
LABEL description="CUDA-enabled audio processing service"

RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash appuser

WORKDIR /app

# .venv 복사 (uv 스테이지에서)
COPY --from=uv --chown=appuser:appuser /app/.venv /app/.venv

# 프로젝트 파일들 복사
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser . /app/

# proto 생성 파일들 복사 (proto-builder 스테이지에서) - 루트로 복사
COPY --from=proto-builder --chown=appuser:appuser /app/audio_service_pb2.py /app/
COPY --from=proto-builder --chown=appuser:appuser /app/audio_service_pb2_grpc.py /app/

USER appuser

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:/app/src"

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]