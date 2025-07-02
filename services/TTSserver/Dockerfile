# services/TTSserver/Dockerfile
# UV를 사용한 의존성 설치 및 proto 컴파일
FROM ghcr.io/astral-sh/uv:python3.10-bookworm-slim AS builder

WORKDIR /app

# 워크스페이스 루트의 의존성 파일들 복사
COPY uv.lock pyproject.toml ./
COPY shared/ ./shared/
COPY services/TTSserver/ ./services/TTSserver/


RUN apt-get update && \
    apt-get install -y protobuf-compiler && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash --uid 1001 appuser && \
    chown -R appuser:appuser /app

# appuser로 전환하여 의존성 설치
USER appuser

RUN uv sync --frozen --no-dev && \
    uv run python -m grpc_tools.protoc \
        --python_out=./services/TTSserver/src \
        --grpc_python_out=./services/TTSserver/src \
        --proto_path=./shared/proto \
        ./shared/proto/audio_service.proto


# 최종 실행 이미지 (CUDA 지원)
FROM nvidia/cuda:12.5.1-runtime-ubuntu22.04

# uv 바이너리 복사
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 메타데이터
LABEL maintainer="lghmk2@gmail.com"
LABEL description="CUDA-enabled TTS service"

# 환경 변수 설정
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 시스템 의존성 설치 및 사용자 생성  
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        ffmpeg && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash --uid 1001 appuser && \
    ln -sf /usr/bin/python3 /usr/local/bin/python

WORKDIR /app

# 전체 앱 디렉토리 복사 (의존성, shared 모듈, 소스 코드, proto 파일 포함)
COPY --from=builder --chown=appuser:appuser /app /app

# models 디렉토리 생성
RUN mkdir -p /app/models && \
    chown -R appuser:appuser /app/models

USER appuser

# 환경 변수 설정 (사용자 전환 후)
ENV PYTHONPATH="/app/services/TTSserver/src"
ENV HF_HOME=/app/models
ENV CUDA_VISIBLE_DEVICES=0

# 포트 노출
EXPOSE 50051

# 애플리케이션 실행
WORKDIR /app/services/TTSserver
ENTRYPOINT ["uv", "run", "python", "src/server.py"]