
# 멀티 스테이지 빌드를 위한 베이스 이미지
FROM python:3.9-slim as base

# 시스템 의존성 설치
RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성 설치 스테이지
FROM base as dependencies

WORKDIR /app

# requirements 복사 및 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# 프로토콜 버퍼 컴파일 스테이지
FROM dependencies as proto-builder

# protoc 설치
RUN apt-get update && apt-get install -y protobuf-compiler && \
    rm -rf /var/lib/apt/lists/*

# proto 파일 복사 및 컴파일
COPY proto/ ./proto/
RUN python -m grpc_tools.protoc \
    --python_out=./src \
    --grpc_python_out=./src \
    --proto_path=./proto \
    ./proto/audio_service.proto

# 최종 실행 이미지
FROM base as runtime

WORKDIR /app

# Python 패키지 복사
COPY --from=dependencies /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# 애플리케이션 코드 복사
COPY src/ ./src/
COPY --from=proto-builder /app/src/audio_service_pb2.py ./src/
COPY --from=proto-builder /app/src/audio_service_pb2_grpc.py ./src/

# 모델 캐시 디렉토리 생성
RUN mkdir -p /app/models && \
    chmod 755 /app/models

# 비 root 사용자 생성 및 권한 설정
RUN useradd -m -u 1001 appuser && \
    chown -R appuser:appuser /app
USER appuser

# 환경 변수 설정
ENV PYTHONPATH=/app/src
ENV MODEL_CACHE_DIR=/app/models
ENV GRPC_PORT=50051
ENV LOG_LEVEL=INFO

# 헬스 체크 스크립트
COPY scripts/healthcheck.py /app/scripts/
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python /app/scripts/healthcheck.py

# 포트 노출
EXPOSE 50051

# 시작 명령
CMD ["python", "/app/src/server.py"]