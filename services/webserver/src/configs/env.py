# services/websocket-service/config.py
import os
from pydantic import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """애플리케이션 설정"""
    
    # 서버 설정
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # CORS 설정
    allowed_origins: list[str] = ["*"]
    allowed_methods: list[str] = ["*"]
    allowed_headers: list[str] = ["*"]
    
    # WebSocket 설정
    websocket_timeout: int = 60
    max_connections: int = 100
    
    # 마이크로서비스 주소 (나중에 gRPC 연동용)
    stt_service_url: str = "stt-service:50051"
    text_processor_service_url: str = "text-processor-service:50052"
    tts_service_url: str = "tts-service:50053"
    
    # 로깅 설정
    log_level: str = "INFO"
    log_format: str = "json"
    
    # 개발 환경 설정
    reload: bool = False
    
    class Config:
        env_file = ".env"
        env_prefix = "WEBSOCKET_"

# 전역 설정 인스턴스
settings = Settings()

def get_settings() -> Settings:
    """설정 인스턴스 반환"""
    return settings