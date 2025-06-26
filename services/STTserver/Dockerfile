# services/STTserver/Dockerfile
# UV를 사용한 의존성 설치 스테이지
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS uv

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

# 프로젝트 의존성 파일들 복사
COPY uv.lock pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev

# 프로토콜 버퍼 컴파일 스테이지
FROM uv AS proto-builder

# protoc 설치
RUN apt-get update && apt-get install -y \
    protobuf-compiler \
    && rm -rf /var/lib/apt/lists/*

# proto 컴파일을 위한 grpcio-tools 설치
RUN --mount=type=cache,target=/root/.cache/uv \
    uv add grpcio-tools --no-sync

# proto 파일 복사 및 컴파일 (현재 디렉토리의 proto 폴더 사용)
COPY proto/ ./proto/
RUN mkdir -p ./src && \
    uv run python -m grpc_tools.protoc \
        --python_out=./src \
        --grpc_python_out=./src \
        --proto_path=./proto \
        ./proto/audio_service.proto

# 최종 실행 이미지 (CUDA 지원)
FROM nvidia/cuda:12.5.1-runtime-ubuntu22.04

# 메타데이터
LABEL maintainer="your-team@company.com"
LABEL description="CUDA-enabled audio processing service"

# 환경 변수 설정
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 시스템 의존성 설치 및 사용자 생성
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3.11 \
        python3.11-distutils \
        ffmpeg \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.11 /usr/bin/python \
    && ln -sf /usr/bin/python3.11 /usr/bin/python3 \
    && useradd --create-home --shell /bin/bash --uid 1001 appuser

WORKDIR /app

# UV 가상환경 복사
COPY --from=uv --chown=appuser:appuser /app/.venv /app/.venv

# 프로젝트 파일들 복사
COPY --chown=appuser:appuser src/ /app/src/
COPY --chown=appuser:appuser . /app/
COPY --chown=appuser:appuser scripts/ /app/scripts/

# proto 생성 파일들 복사 (proto-builder 스테이지에서)
COPY --from=proto-builder --chown=appuser:appuser /app/src/audio_service_pb2.py /app/src/
COPY --from=proto-builder --chown=appuser:appuser /app/src/audio_service_pb2_grpc.py /app/src/

# 모델 및 로그 디렉토리 생성
RUN mkdir -p /app/models /app/logs && \
    chown -R appuser:appuser /app/models /app/logs

USER appuser

# 환경 변수 설정
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src:/app"

# 포트 노출
EXPOSE 50051

# 헬스 체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=90s --retries=3 \
    CMD python /app/scripts/healthcheck.py || exit 1

# 볼륨 설정
VOLUME ["/app/models", "/app/logs"]

# 애플리케이션 실행
CMD ["python", "/app/src/server.py"]