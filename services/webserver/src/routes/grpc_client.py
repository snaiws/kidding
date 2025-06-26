# service/webserver/src/grpc_client.py
"""
gRPC 클라이언트 모듈
STT 서버와 통신하기 위한 gRPC 클라이언트 구현
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
            # Proto 파일이 없으면 연결하지 않음
            if not PROTO_AVAILABLE:
                logger.warning("⚠️ Proto 파일이 없어 gRPC 연결을 건너뜁니다")
                return False
            
            logger.info(f"🔗 gRPC 서버 연결 시도: {self.host}:{self.port}")
            
            # gRPC 채널 생성
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
            
            # gRPC stub 생성
            self.stub = audio_service_pb2_grpc.AudioProcessingStub(self.channel)
            logger.info("📡 gRPC Stub 생성 완료")
            
            # 연결 테스트
            await self._test_connection()
            
            logger.info(f"✅ STT gRPC 서버 연결 성공: {self.host}:{self.port}")
            return True
            
        except Exception as e:
            logger.error(f"❌ STT gRPC 서버 연결 실패: {e}")
            logger.error(f"🔍 연결 시도 주소: {self.host}:{self.port}")
            logger.error(f"🔍 Proto 사용 가능: {PROTO_AVAILABLE}")
            return False
    
    async def _test_connection(self):
        """연결 테스트"""
        try:
            if PROTO_AVAILABLE and self.stub:
                # 실제 헬스 체크 호출
                request = audio_service_pb2.HealthCheckRequest(service="stt")
                response = await asyncio.wait_for(
                    self.stub.HealthCheck(request),
                    timeout=5.0
                )
                
                # 응답 상태 확인 (enum 참조 방법 수정)
                if hasattr(response, 'status'):
                    # 일반적으로 SERVING = 1, NOT_SERVING = 0
                    if response.status != 1:  # SERVING 상태가 아닌 경우
                        raise Exception(f"서비스가 준비되지 않음: {response.status}")
            else:
                # Proto 없이 단순 연결 확인
                await asyncio.wait_for(
                    self.channel.channel_ready(),
                    timeout=5.0
                )
        except Exception as e:
            raise Exception(f"연결 테스트 실패: {e}")
    
    async def process_stt(self, audio_data: bytes, session_id: int, language: str = "korean") -> Dict[str, Any]:
        """STT 처리 요청"""
        try:
            start_time = time.time()
            
            logger.info(f"🎤 STT 처리 시작 (세션: {session_id}, 오디오: {len(audio_data)} bytes)")
            
            if PROTO_AVAILABLE and self.stub and self.channel:
                # 실제 gRPC 호출
                request = audio_service_pb2.STTRequest(
                    request_id=f"session_{session_id}_{int(time.time() * 1000)}",
                    audio_data=audio_data,
                    config=audio_service_pb2.STTConfig(
                        language=language,
                        enable_vad=True,
                        sample_rate=16000
                        # format은 proto 파일 정의에 따라 조정 필요
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
                # Proto 파일이나 연결이 없는 경우
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
            logger.error(f"❌ gRPC 연결 종료 실패: {e}")
    
    def is_connected(self) -> bool:
        """연결 상태 확인"""
        return (self.channel is not None and 
                PROTO_AVAILABLE and 
                self.stub is not None)

# 글로벌 STT 클라이언트 인스턴스
_stt_client: Optional[STTGRPCClient] = None

async def get_stt_client() -> STTGRPCClient:
    """STT 클라이언트 싱글톤 인스턴스 반환"""
    global _stt_client
    
    if _stt_client is None:
        # 환경 변수에서 호스트/포트 읽기
        import os
        host = os.getenv("STT_GRPC_HOST", "kidding-stt")  # Docker 네트워크의 STT 서버 alias
        port = int(os.getenv("STT_GRPC_PORT", "50051"))
        
        _stt_client = STTGRPCClient(host=host, port=port)
        
        # 연결 시도
        try:
            connected = await _stt_client.connect()
            if not connected:
                logger.warning("⚠️ STT 서버에 연결할 수 없습니다. STT 기능이 비활성화됩니다.")
        except Exception as e:
            logger.error(f"❌ STT 클라이언트 초기화 실패: {e}")
    
    return _stt_client

async def cleanup_stt_client():
    """STT 클라이언트 정리"""
    global _stt_client
    if _stt_client:
        await _stt_client.close()
        _stt_client = None
        logger.info("🧹 STT 클라이언트 정리 완료")