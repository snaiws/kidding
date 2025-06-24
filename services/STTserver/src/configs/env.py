
import os
from dataclasses import dataclass
from typing import Optional

@dataclass
class ModelConfig:
    """모델 설정"""
    stt_model_name: str = "openai/whisper-large-v3"
    tts_model_name: str = "microsoft/speecht5_tts"
    device: str = "cuda" if os.environ.get("USE_GPU", "true").lower() == "true" else "cpu"
    cache_dir: str = "/app/models"
    enable_quantization: bool = True
    max_audio_length: int = 300  # 5분

@dataclass
class ServerConfig:
    """서버 설정"""
    host: str = "0.0.0.0"
    port: int = 50051
    max_workers: int = 4
    max_message_size: int = 100 * 1024 * 1024  # 100MB
    enable_compression: bool = True

@dataclass
class AppConfig:
    """애플리케이션 설정"""
    model: ModelConfig
    server: ServerConfig
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "AppConfig":
        """환경변수에서 설정 로드"""
        return cls(
            model=ModelConfig(
                stt_model_name=os.environ.get("STT_MODEL", "openai/whisper-large-v3"),
                tts_model_name=os.environ.get("TTS_MODEL", "microsoft/speecht5_tts"),
                device=os.environ.get("DEVICE", "cuda" if os.environ.get("USE_GPU", "true").lower() == "true" else "cpu"),
                cache_dir=os.environ.get("MODEL_CACHE_DIR", "/app/models"),
            ),
            server=ServerConfig(
                host=os.environ.get("GRPC_HOST", "0.0.0.0"),
                port=int(os.environ.get("GRPC_PORT", "50051")),
                max_workers=int(os.environ.get("MAX_WORKERS", "4")),
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO")
        )