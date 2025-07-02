# services/webserver/Dockerfile
# UV를 사용한 의존성 설치 및 proto 컴파일
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# 워크스페이스 루트의 의존성 파일들 복사
COPY uv.lock pyproject.toml ./
COPY shared/ ./shared/
COPY services/webserver/ ./services/webserver/

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# protoc 설치 및 proto 컴파일
RUN apt-get update && \
    apt-get install -y protobuf-compiler && \
    mkdir -p ./services/webserver/src && \
    uv run python -m grpc_tools.protoc \
        --python_out=./services/webserver/src \
        --grpc_python_out=./services/webserver/src \
        --proto_path=./shared/proto \
        ./shared/proto/audio_service.proto && \
    rm -rf /var/lib/apt/lists/*

# 최종 실행 이미지 
FROM python:3.12-slim-bookworm

# 메타데이터
LABEL maintainer="lghmk2@gmail.com"
LABEL description="kidding webserver"

# 환경 변수 설정
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 시스템 의존성 설치 및 사용자 생성
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --shell /bin/bash --uid 1001 appuser

WORKDIR /app

# 전체 앱 디렉토리 복사 (의존성, shared 모듈, 소스 코드, proto 파일 포함)
COPY --from=builder --chown=appuser:appuser /app /app

# src 디렉토리로 워킹 디렉토리 변경
WORKDIR /app/services/webserver

USER appuser

# 환경 변수 설정 (사용자 전환 후)
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/services/webserver/src"

# 포트 노출
EXPOSE 8000

# 애플리케이션 실행
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]