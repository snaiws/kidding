# services/websocket-service/Dockerfile
FROM python:3.11-slim

# 메타데이터
LABEL maintainer="EuKidding Team"
LABEL description="WebSocket Service for EuKidding Voice Converter"

# 작업 디렉토리 설정
WORKDIR /app

# 시스템 패키지 업데이트 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Python 의존성 먼저 복사 및 설치 (캐시 최적화)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 애플리케이션 파일 복사
COPY . .

# 비root 사용자 생성 (보안)
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

# 포트 노출
EXPOSE 8001

# 헬스체크
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8001/health || exit 1

# 애플리케이션 실행
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]