# services/STTserver/src/server.py
import grpc
from concurrent import futures
import logging
import signal
import sys
import time
from typing import Dict, Any

# proto 파일에서 생성된 모듈들
import audio_service_pb2
import audio_service_pb2_grpc

from models.stt_model import STTModel
# from models.tts_model import TTSModel
from configs.env import AppConfig
from audio_processor import AudioProcessor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioProcessingServicer(audio_service_pb2_grpc.AudioProcessingServicer):
    """gRPC 오디오 처리 서비스"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.stt_model = None
        # self.tts_model = None
        self.audio_processor = AudioProcessor()
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """모델 초기화"""
        try:
            logger.info("모델 초기화 시작")
            
            # STT 모델 초기화
            self.stt_model = STTModel(
                model_name=self.config.model.stt_model_name,
                device=self.config.model.device,
                cache_dir=self.config.model.cache_dir
            )
            self.stt_model.load_model()
            
            logger.info("모델 초기화 완료")
            
        except Exception as e:
            logger.error(f"모델 초기화 실패: {e}")
            raise
    
    def ProcessSTT(self, request, context):
        """STT 처리 (Unary RPC)"""
        try:
            logger.info(f"🎤 STT 요청 처리 시작: {request.request_id}")
            start_time = time.time()
            
            # 오디오 데이터 전처리
            audio_data, sr = self.audio_processor.load_audio_from_bytes(
                request.audio_data, 
                target_sr=request.config.sample_rate or 16000
            )
            
            # VAD 체크 (선택적)
            if request.config.enable_vad:
                if not self.audio_processor.detect_speech_activity(audio_data, sr):
                    logger.warning(f"⚠️ 음성이 감지되지 않음: {request.request_id}")
                    return audio_service_pb2.STTResponse(
                        request_id=request.request_id,
                        transcription="",
                        confidence=0.0,
                        error="음성이 감지되지 않았습니다"
                    )
            
            # 오디오 정규화
            audio_data = self.audio_processor.normalize_audio(audio_data)
            
            # STT 모델로 처리
            result = self.stt_model.process(
                audio_data=audio_data,
                language=request.config.language or "korean"
            )
            
            processing_time = (time.time() - start_time) * 1000
            
            # 응답 생성
            response = audio_service_pb2.STTResponse(
                request_id=request.request_id,
                transcription=result["transcription"],
                confidence=result["confidence"],
                stats=audio_service_pb2.ProcessingStats(
                    processing_time_ms=int(processing_time),
                    model_used=result["model_used"],
                    timestamp=int(time.time()),
                    audio_duration_ms=int(result.get("audio_length_ms", 0))  # stt_model에서 계산된 값 사용
                )
            )
            
            logger.info(f"✅ STT 요청 처리 완료: {request.request_id}")
            logger.info(f"📝 STT 결과: \"{result['transcription']}\" (신뢰도: {result['confidence']:.2f}, 처리시간: {processing_time:.1f}ms)")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ STT 처리 중 오류 ({request.request_id}): {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"STT 처리 실패: {str(e)}")
            return audio_service_pb2.STTResponse(
                request_id=request.request_id,
                error=str(e)
            )
    
    def ProcessTTS(self, request, context):
        """TTS 처리 (향후 구현)"""
        logger.warning(f"⚠️ TTS 기능은 아직 구현되지 않음: {request.request_id}")
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("TTS 기능은 아직 구현되지 않았습니다")
        return audio_service_pb2.TTSResponse(
            request_id=request.request_id,
            error="TTS 기능은 아직 구현되지 않았습니다"
        )
    
    def HealthCheck(self, request, context):
        """헬스 체크"""
        try:
            logger.debug(f"🔍 헬스 체크 요청: {request.service}")
            
            # STT 모델 상태 확인
            stt_available = self.stt_model.is_loaded() if self.stt_model else False
            tts_available = False  # TTS는 아직 구현 안됨
            
            # 서비스별 상태
            services = {}
            
            if request.service in ["stt", "all"]:
                services["stt"] = audio_service_pb2.ServiceHealth(
                    available=stt_available,
                    model_name=self.config.model.stt_model_name,
                    version="1.0",
                    uptime_seconds=int(time.time())
                )
            
            if request.service in ["tts", "all"]:
                services["tts"] = audio_service_pb2.ServiceHealth(
                    available=tts_available,
                    model_name="not_implemented",
                    version="0.0",
                    uptime_seconds=0
                )
            
            # 전체 서비스 상태 결정
            if request.service == "stt":
                status = audio_service_pb2.SERVING if stt_available else audio_service_pb2.NOT_SERVING
            elif request.service == "tts":
                status = audio_service_pb2.NOT_SERVING  # TTS 미구현
            else:  # "all" 또는 기타
                status = audio_service_pb2.SERVING if stt_available else audio_service_pb2.NOT_SERVING
            
            response = audio_service_pb2.HealthCheckResponse(
                status=status,
                services=services
            )
            
            logger.debug(f"✅ 헬스 체크 완료: {status}")
            return response
            
        except Exception as e:
            logger.error(f"❌ 헬스 체크 실패: {e}")
            return audio_service_pb2.HealthCheckResponse(
                status=audio_service_pb2.NOT_SERVING
            )

class GRPCServer:
    """gRPC 서버 관리자"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.server = None
        self.servicer = None
    
    def start(self) -> None:
        """서버 시작"""
        try:
            logger.info("🚀 gRPC 서버 시작")
            
            # 서버 옵션 설정
            options = [
                ('grpc.max_send_message_length', self.config.server.max_message_size),
                ('grpc.max_receive_message_length', self.config.server.max_message_size),
                ('grpc.keepalive_time_ms', 30000),
                ('grpc.keepalive_timeout_ms', 5000),
                ('grpc.keepalive_permit_without_calls', True),
                ('grpc.http2.max_pings_without_data', 0),
                ('grpc.http2.min_time_between_pings_ms', 10000),
                ('grpc.http2.min_ping_interval_without_data_ms', 300000),
            ]
            
            # 서버 생성
            self.server = grpc.server(
                futures.ThreadPoolExecutor(max_workers=self.config.server.max_workers),
                options=options
            )
            
            # 서비스 등록
            self.servicer = AudioProcessingServicer(self.config)
            audio_service_pb2_grpc.add_AudioProcessingServicer_to_server(
                self.servicer, self.server
            )
            
            # 포트 바인딩
            listen_addr = f"{self.config.server.host}:{self.config.server.port}"
            self.server.add_insecure_port(listen_addr)
            
            # 서버 시작
            self.server.start()
            logger.info(f"✅ gRPC 서버가 {listen_addr}에서 시작되었습니다")
            
            # 종료 시그널 핸들러 등록
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
            
            # 서버 대기
            self.server.wait_for_termination()
            
        except Exception as e:
            logger.error(f"❌ 서버 시작 실패: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        """종료 시그널 핸들러"""
        logger.info(f"🔄 종료 시그널 수신: {signum}")
        self.stop()
    
    def stop(self, grace_period: int = 30):
        """서버 정지"""
        if self.server:
            logger.info("🔄 gRPC 서버 정지 중...")
            self.server.stop(grace_period)
            logger.info("✅ gRPC 서버 정지 완료")

def main():
    """메인 함수"""
    try:
        # 설정 로드
        config = AppConfig.from_env()
        
        # 로깅 레벨 설정
        logging.getLogger().setLevel(getattr(logging, config.log_level.upper()))
        
        logger.info("=== 🎤 STT gRPC 서버 시작 ===")
        logger.info(f"STT 모델: {config.model.stt_model_name}")
        logger.info(f"디바이스: {config.model.device}")
        logger.info(f"서버 주소: {config.server.host}:{config.server.port}")
        
        # 서버 시작
        server = GRPCServer(config)
        server.start()
        
    except KeyboardInterrupt:
        logger.info("🔄 사용자 인터럽트로 서버 종료")
    except Exception as e:
        logger.error(f"❌ 서버 실행 중 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()