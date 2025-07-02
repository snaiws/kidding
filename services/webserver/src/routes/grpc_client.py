# service/webserver/src/grpc_client.py
"""
gRPC 클라이언트 모듈 (proto 파일 매칭 버전)
STT 서버와 TTS 서버와 통신하기 위한 gRPC 클라이언트 구현
"""
import grpc
import asyncio
import logging
from typing import Optional, Dict, Any
import time
import sys
import os

# proto 파일에서 생성된 모듈들 임포트 시도
PROTO_AVAILABLE = False
try:
    import audio_service_pb2
    import audio_service_pb2_grpc
    PROTO_AVAILABLE = True
    logging.info("✅ Proto 파일 로드 성공")
except ImportError as e:
    PROTO_AVAILABLE = False
    logging.warning(f"⚠️ Proto 파일을 찾을 수 없습니다: {e}")

logger = logging.getLogger(__name__)

class STTGRPCClient:
    """STT gRPC 클라이언트"""
    
    def __init__(self, host: str = "stt-server", port: int = 50051, timeout: int = 30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.channel = None
        self.stub = None
        
    async def connect(self) -> bool:
        """gRPC 서버에 연결"""
        try:
            if not PROTO_AVAILABLE:
                logger.warning("⚠️ Proto 파일이 없어 gRPC 연결을 건너뜁니다")
                return False
            
            logger.info(f"🔗 STT gRPC 서버 연결 시도: {self.host}:{self.port}")
            
            self.channel = grpc.aio.insecure_channel(
                f"{self.host}:{self.port}",
                options=[
                    ('grpc.keepalive_time_ms', 30000),
                    ('grpc.keepalive_timeout_ms', 5000),
                    ('grpc.keepalive_permit_without_calls', True),
                    ('grpc.http2.max_pings_without_data', 0),
                    ('grpc.http2.min_time_between_pings_ms', 10000),
                    ('grpc.http2.min_ping_interval_without_data_ms', 300000),
                ]
            )
            
            self.stub = audio_service_pb2_grpc.AudioProcessingStub(self.channel)
            logger.info("📡 STT gRPC Stub 생성 완료")
            
            await self._test_connection()
            
            logger.info(f"✅ STT gRPC 서버 연결 성공: {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"❌ STT gRPC 서버 연결 실패: {e}")
            return False
    
    async def _test_connection(self):
        """연결 테스트"""
        try:
            if PROTO_AVAILABLE and self.stub:
                request = audio_service_pb2.HealthCheckRequest(service="stt")
                response = await asyncio.wait_for(
                    self.stub.HealthCheck(request),
                    timeout=5.0
                )
                
                if hasattr(response, 'status'):
                    if response.status != 1:  # SERVING 상태가 아닌 경우
                        raise Exception(f"서비스가 준비되지 않음: {response.status}")
        except Exception as e:
            raise Exception(f"연결 테스트 실패: {e}")
    
    async def process_stt(self, audio_data: bytes, session_id: int, language: str = "korean") -> Dict[str, Any]:
        """STT 처리 요청"""
        try:
            start_time = time.time()
            
            logger.info(f"🎤 STT 처리 시작 (세션: {session_id}, 오디오: {len(audio_data)} bytes)")
            
            if PROTO_AVAILABLE and self.stub and self.channel:
                request = audio_service_pb2.STTRequest(
                    request_id=f"session_{session_id}_{int(time.time() * 1000)}",
                    audio_data=audio_data,
                    config=audio_service_pb2.STTConfig(
                        language=language,
                        enable_vad=True,
                        sample_rate=16000,
                        format=audio_service_pb2.PCM_16
                    )
                )
                
                response = await asyncio.wait_for(
                    self.stub.ProcessSTT(request),
                    timeout=self.timeout
                )
                
                processing_time = (time.time() - start_time) * 1000
                
                if hasattr(response, 'error') and response.error:
                    logger.error(f"❌ STT 서버 오류 (세션: {session_id}): {response.error}")
                    return {
                        "success": False,
                        "error": response.error,
                        "transcription": "",
                        "confidence": 0.0
                    }
                
                logger.info(f"✅ STT 처리 완료 (세션: {session_id}, 처리시간: {processing_time:.1f}ms)")
                logger.info(f"📝 STT 결과: \"{response.transcription}\" (신뢰도: {response.confidence:.2f})")
                
                return {
                    "success": True,
                    "transcription": response.transcription,
                    "confidence": response.confidence,
                    "processing_time_ms": processing_time,
                    "request_id": getattr(response, 'request_id', '')
                }
            else:
                processing_time = (time.time() - start_time) * 1000
                logger.warning(f"⚠️ gRPC 연결 없음, STT 처리 건너뜀 (세션: {session_id})")
                
                return {
                    "success": False,
                    "error": "gRPC 서버에 연결되지 않음",
                    "transcription": "",
                    "confidence": 0.0,
                    "processing_time_ms": processing_time
                }
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ STT 처리 타임아웃 (세션: {session_id})")
            return {
                "success": False,
                "error": "STT 처리 타임아웃",
                "transcription": "",
                "confidence": 0.0
            }
        except Exception as e:
            logger.error(f"❌ STT 처리 실패 (세션: {session_id}): {e}")
            return {
                "success": False,
                "error": str(e),
                "transcription": "",
                "confidence": 0.0
            }
    
    async def close(self):
        """연결 종료"""
        try:
            if self.channel:
                await self.channel.close()
                logger.info("🔌 STT gRPC 연결 종료")
        except Exception as e:
            logger.error(f"❌ STT gRPC 연결 종료 실패: {e}")
    
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return (self.channel is not None and 
                PROTO_AVAILABLE and 
                self.stub is not None)


class TTSGRPCClient:
    """TTS gRPC 클라이언트 (proto 파일 매칭)"""
    
    def __init__(self, host: str = "tts-server", port: int = 50051, timeout: int = 30):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.channel = None
        self.stub = None
        
    async def connect(self) -> bool:
        """gRPC 서버에 연결"""
        try:
            if not PROTO_AVAILABLE:
                logger.warning("⚠️ Proto 파일이 없어 gRPC 연결을 건너뜁니다")
                return False
            
            logger.info(f"🔗 TTS gRPC 서버 연결 시도: {self.host}:{self.port}")
            
            self.channel = grpc.aio.insecure_channel(
                f"{self.host}:{self.port}",
                options=[
                    ('grpc.keepalive_time_ms', 30000),
                    ('grpc.keepalive_timeout_ms', 5000),
                    ('grpc.keepalive_permit_without_calls', True),
                    ('grpc.http2.max_pings_without_data', 0),
                    ('grpc.http2.min_time_between_pings_ms', 10000),
                    ('grpc.http2.min_ping_interval_without_data_ms', 300000),
                ]
            )
            
            self.stub = audio_service_pb2_grpc.AudioProcessingStub(self.channel)
            logger.info("📡 TTS gRPC Stub 생성 완료")
            
            await self._test_connection()
            
            logger.info(f"✅ TTS gRPC 서버 연결 성공: {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"❌ TTS gRPC 서버 연결 실패: {e}")
            return False
    
    async def _test_connection(self):
        """연결 테스트"""
        try:
            if PROTO_AVAILABLE and self.stub:
                request = audio_service_pb2.HealthCheckRequest(service="tts")
                response = await asyncio.wait_for(
                    self.stub.HealthCheck(request),
                    timeout=5.0
                )
                
                if hasattr(response, 'status'):
                    if response.status != 1:  # SERVING 상태가 아닌 경우
                        raise Exception(f"서비스가 준비되지 않음: {response.status}")
        except Exception as e:
            raise Exception(f"연결 테스트 실패: {e}")
    
    async def process_tts(self, text: str, session_id: int, voice: str = "female", 
                         language: str = "korean", speed: float = 1.0, pitch: float = 1.0) -> Dict[str, Any]:
        """TTS 처리 요청 (proto 파일 매칭)"""
        try:
            start_time = time.time()
            
            logger.info(f"🔊 TTS 처리 시작 (세션: {session_id}, 텍스트: '{text[:50]}{'...' if len(text) > 50 else ''}')")
            
            if PROTO_AVAILABLE and self.stub and self.channel:
                # proto 파일에 맞는 TTS 설정
                tts_config = audio_service_pb2.TTSConfig(
                    language=language,
                    voice=voice,
                    speed=speed,
                    pitch=pitch,
                    format=audio_service_pb2.WAV,
                    sample_rate=22050  # XTTS-v2 기본값
                )
                
                request = audio_service_pb2.TTSRequest(
                    request_id=f"session_{session_id}_{int(time.time() * 1000)}",
                    text=text,
                    config=tts_config
                )
                
                response = await asyncio.wait_for(
                    self.stub.ProcessTTS(request),
                    timeout=self.timeout
                )
                
                processing_time = (time.time() - start_time) * 1000
                
                if hasattr(response, 'error') and response.error:
                    logger.error(f"❌ TTS 서버 오류 (세션: {session_id}): {response.error}")
                    return {
                        "success": False,
                        "error": response.error,
                        "audio_data": None
                    }
                
                logger.info(f"✅ TTS 처리 완료 (세션: {session_id}, 처리시간: {processing_time:.1f}ms)")
                logger.info(f"🔊 TTS 결과: {len(response.audio_data)}바이트 오디오 데이터")
                
                return {
                    "success": True,
                    "audio_data": response.audio_data,
                    "processing_time_ms": processing_time,
                    "request_id": getattr(response, 'request_id', ''),
                    "stats": getattr(response, 'stats', None)
                }
            else:
                processing_time = (time.time() - start_time) * 1000
                logger.warning(f"⚠️ gRPC 연결 없음, TTS 처리 건너뜀 (세션: {session_id})")
                
                return {
                    "success": False,
                    "error": "gRPC 서버에 연결되지 않음",
                    "audio_data": None,
                    "processing_time_ms": processing_time
                }
            
        except asyncio.TimeoutError:
            logger.error(f"⏰ TTS 처리 타임아웃 (세션: {session_id})")
            return {
                "success": False,
                "error": "TTS 처리 타임아웃",
                "audio_data": None
            }
        except Exception as e:
            logger.error(f"❌ TTS 처리 실패 (세션: {session_id}): {e}")
            return {
                "success": False,
                "error": str(e),
                "audio_data": None
            }
    
    async def close(self):
        """연결 종료"""
        try:
            if self.channel:
                await self.channel.close()
                logger.info("🔌 TTS gRPC 연결 종료")
        except Exception as e:
            logger.error(f"❌ TTS gRPC 연결 종료 실패: {e}")
    
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return (self.channel is not None and 
                PROTO_AVAILABLE and 
                self.stub is not None)


# 글로벌 클라이언트 인스턴스들
_stt_client: Optional[STTGRPCClient] = None
_tts_client: Optional[TTSGRPCClient] = None

async def get_stt_client() -> STTGRPCClient:
    """STT 클라이언트 싱글톤 인스턴스 반환"""
    global _stt_client
    
    if _stt_client is None:
        host = os.getenv("STT_GRPC_HOST", "kidding-stt")
        port = int(os.getenv("PORT_STT_GRPC", "50051"))
        
        _stt_client = STTGRPCClient(host=host, port=port)
        
        try:
            connected = await _stt_client.connect()
            if not connected:
                logger.warning("⚠️ STT 서버에 연결할 수 없습니다. STT 기능이 비활성화됩니다.")
        except Exception as e:
            logger.error(f"❌ STT 클라이언트 초기화 실패: {e}")
    
    return _stt_client

async def get_tts_client() -> TTSGRPCClient:
    """TTS 클라이언트 싱글톤 인스턴스 반환"""
    global _tts_client
    
    if _tts_client is None:
        host = os.getenv("TTS_GRPC_HOST", "kidding-tts")
        port = int(os.getenv("TTS_GRPC_PORT", "50051"))
        
        _tts_client = TTSGRPCClient(host=host, port=port)
        
        try:
            connected = await _tts_client.connect()
            if not connected:
                logger.warning("⚠️ TTS 서버에 연결할 수 없습니다. TTS 기능이 비활성화됩니다.")
        except Exception as e:
            logger.error(f"❌ TTS 클라이언트 초기화 실패: {e}")
    
    return _tts_client

async def cleanup_grpc_clients():
    """모든 gRPC 클라이언트 정리"""
    global _stt_client, _tts_client
    
    if _stt_client:
        await _stt_client.close()
        _stt_client = None
        logger.info("🧹 STT 클라이언트 정리 완료")
    
    if _tts_client:
        await _tts_client.close()
        _tts_client = None
        logger.info("🧹 TTS 클라이언트 정리 완료")

# 호환성을 위한 별칭
cleanup_stt_client = cleanup_grpc_clients