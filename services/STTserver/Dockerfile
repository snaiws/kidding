# UV 프로젝트 최적화 멀티 스테이지 빌드
FROM nvidia/cuda:12.5.1-cudnn-devel-ubuntu22.04 as base

# 환경 변수 설정
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# UV 설치
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# UV 의존성 설치 스테이지
FROM base as uv-deps

WORKDIR /app

# Python 버전 설정 및 가상환경 생성
RUN uv python install 3.11
ENV UV_PROJECT_ENVIRONMENT=/app/.venv

# 의존성 파일 복사
COPY pyproject.toml uv.lock ./

# 의존성 설치 (프로덕션 전용)
RUN uv sync --frozen --no-dev --no-install-project

# 프로토콜 버퍼 컴파일 스테이지
FROM uv-deps as proto-builder

# protoc 및 grpcio-tools 설치
RUN apt-get update && apt-get install -y protobuf-compiler && \
    rm -rf /var/lib/apt/lists/* && \
    uv add --no-sync grpcio-tools

# proto 파일 복사 및 컴파일
COPY proto/ ./proto/
RUN mkdir -p ./src && \
    if [ -f "./proto/audio_service.proto" ]; then \
        uv run python -m grpc_tools.protoc \
            --python_out=./src \
            --grpc_python_out=./src \
            --proto_path=./proto \
            ./proto/audio_service.proto; \
    fi

# 최종 실행 이미지 (경량화)
FROM nvidia/cuda:12.5.1-runtime-ubuntu22.04 as runtime

# 런타임 의존성만 설치
RUN apt-get update && apt-get install -y \
    --no-install-recommends \
    ffmpeg \
    libprotobuf32 \
    python3.11 \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python

# UV 복사 (런타임 관리용)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/

WORKDIR /app

# 가상환경 및 의존성 복사
COPY --from=uv-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# 사용자 설정
RUN groupadd -r appgroup && \
    useradd -r -g appgroup -u 1001 -m appuser && \
    mkdir -p /app/{src,models,logs,scripts} && \
    chown -R appuser:appgroup /app

# 애플리케이션 코드 복사
COPY --chown=appuser:appgroup src/ ./src/
COPY --chown=appuser:appgroup --from=proto-builder /app/src/*_pb2*.py ./src/ 2>/dev/null || true
COPY --chown=appuser:appgroup scripts/ ./scripts/

# pyproject.toml 복사 (UV 프로젝트 정보용)
COPY --chown=appuser:appgroup pyproject.toml ./

USER appuser

# 환경 변수 설정
ENV PYTHONPATH=/app/src:/app \
    MODEL_CACHE_DIR=/app/models \
    LOG_DIR=/app/logs \
    GRPC_PORT=50051 \
    LOG_LEVEL=INFO \
    CUDA_VISIBLE_DEVICES=0

EXPOSE 50051

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python /app/scripts/healthcheck.py || exit 1

VOLUME ["/app/models", "/app/logs"]

# UV를 통한 애플리케이션 실행
CMD ["uv", "run", "python", "/app/src/server.py"]