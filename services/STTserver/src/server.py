
import grpc
from concurrent import futures
import logging
import signal
import sys
import time
from typing import Dict, Any

# proto 파일에서 생성된 모듈들 (실제로는 protoc로 생성)
# import audio_service_pb2
# import audio_service_pb2_grpc

from models.stt_model import STTModel
from models.tts_model import TTSModel
from utils.config import AppConfig
from utils.audio_processor import AudioProcessor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioProcessingServicer:  # audio_service_pb2_grpc.AudioProcessingServicer
    """gRPC 오디오 처리 서비스"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.stt_model = None
        self.tts_model = None
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
            
            # TTS 모델 초기화
            self.tts_model = TTSModel(
                model_name=self.config.model.tts_model_name,
                device=self.config.model.device,
                cache_dir=self.config.model.cache_dir
            )
            self.tts_model.load_model()
            
            logger.info("모델 초기화 완료")
            
        except Exception as e:
            logger.error(f"모델 초기화 실패: {e}")
            raise
    
    def ProcessSTT(self, request, context):
        """STT 처리 (Unary RPC)"""
        try:
            logger.info(f"STT 요청 처리 시작: {request.request_id}")
            
            # 오디오 데이터 전처리
            audio_data, sr = self.audio_processor.load_audio_from_bytes(
                request.audio_data, 
                target_sr=16000
            )
            
            # VAD 체크 (선택적)
            if request.config.enable_vad:
                if not self.audio_processor.detect_speech_activity(audio_data, sr):
                    return self._create_stt_response(
                        request_id=request.request_id,
                        transcription="",
                        confidence=0.0,
                        error_message="음성이 감지되지 않았습니다"
                    )
            
            # 오디오 정규화
            audio_data = self.audio_processor.normalize_audio(audio_data)
            
            # STT 모델로 처리
            result = self.stt_model.process(
                audio_data=audio_data,
                language=request.config.language or "korean"
            )
            
            # 응답 생성
            response = self._create_stt_response(
                request_id=request.request_id,
                transcription=result["transcription"],
                confidence=result["confidence"],
                processing_time_ms=result["processing_time_ms"],
                model_used=result["model_used"]
            )
            
            logger.info(f"STT 요청 처리 완료: {request.request_id}")
            return response
            
        except Exception as e:
            logger.error(f"STT 처리 중 오류: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"STT 처리 실패: {str(e)}")
            return self._create_stt_response(request_id=request.request_id)
    
    def ProcessTTS(self, request, context):
        """TTS 처리 (Unary RPC)"""
        try:
            logger.info(f"TTS 요청 처리 시작: {request.request_id}")
            
            # 입력 텍스트 검증
            if not request.text.strip():
                context.set_code(grpc.StatusCode.INVALID_ARGUMENT)
                context.set_details("입력 텍스트가 비어있습니다")
                return self._create_tts_response(request_id=request.request_id)
            
            # TTS 모델로 처리
            result = self.tts_model.process(
                text=request.text,
                voice_config=request.voice_config
            )
            
            # 응답 생성
            response = self._create_tts_response(
                request_id=request.request_id,
                audio_data=result["audio_data"],
                format=result["format"],
                processing_time_ms=result["processing_time_ms"],
                model_used=result["model_used"]
            )
            
            logger.info(f"TTS 요청 처리 완료: {request.request_id}")
            return response
            
        except Exception as e:
            logger.error(f"TTS 처리 중 오류: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"TTS 처리 실패: {str(e)}")
            return self._create_tts_response(request_id=request.request_id)
    
    def HealthCheck(self, request, context):
        """헬스 체크"""
        try:
            # 모델 상태 확인
            stt_status = self.stt_model.is_loaded() if self.stt_model else False
            tts_status = self.tts_model.is_loaded() if self.tts_model else False
            
            if stt_status and tts_status:
                status = 1  # SERVING
            else:
                status = 2  # NOT_SERVING
            
            return self._create_health_response(status)
            
        except Exception as e:
            logger.error(f"헬스 체크 실패: {e}")
            return self._create_health_response(2)  # NOT_SERVING
    
    def _create_stt_response(self, request_id: str, transcription: str = "", 
                           confidence: float = 0.0, processing_time_ms: float = 0.0,
                           model_used: str = "", error_message: str = ""):
        """STT 응답 생성 헬퍼"""
        # 실제로는 audio_service_pb2.STTResponse() 사용
        return {
            "transcription": transcription,
            "confidence": confidence,
            "request_id": request_id,
            "stats": {
                "processing_time_ms": processing_time_ms,
                "model_used": model_used
            },
            "error": error_message
        }
    
    def _create_tts_response(self, request_id: str, audio_data: bytes = b"",
                           format: str = "WAV", processing_time_ms: float = 0.0,
                           model_used: str = ""):
        """TTS 응답 생성 헬퍼"""
        # 실제로는 audio_service_pb2.TTSResponse() 사용
        return {
            "audio_data": audio_data,
            "format": format,
            "request_id": request_id,
            "stats": {
                "processing_time_ms": processing_time_ms,
                "model_used": model_used
            }
        }
    
    def _create_health_response(self, status: int):
        """헬스 체크 응답 생성 헬퍼"""
        # 실제로는 audio_service_pb2.HealthCheckResponse() 사용
        return {"status": status}

class GRPCServer:
    """gRPC 서버 관리자"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.server = None
        self.servicer = None
    
    def start(self) -> None:
        """서버 시작"""
        try:
            logger.info("gRPC 서버 시작")
            
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
            # audio_service_pb2_grpc.add_AudioProcessingServicer_to_server(
            #     self.servicer, self.server
            # )
            
            # 포트 바인딩
            listen_addr = f"{self.config.server.host}:{self.config.server.port}"
            self.server.add_insecure_port(listen_addr)
            
            # 서버 시작
            self.server.start()
            logger.info(f"gRPC 서버가 {listen_addr}에서 시작되었습니다")
            
            # 종료 시그널 핸들러 등록
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
            
            # 서버 대기
            self.server.wait_for_termination()
            
        except Exception as e:
            logger.error(f"서버 시작 실패: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        """종료 시그널 핸들러"""
        logger.info(f"종료 시그널 수신: {signum}")
        self.stop()
    
    def stop(self, grace_period: int = 30):
        """서버 정지"""
        if self.server:
            logger.info("gRPC 서버 정지 중...")
            self.server.stop(grace_period)
            logger.info("gRPC 서버 정지 완료")

def main():
    """메인 함수"""
    try:
        # 설정 로드
        config = AppConfig.from_env()
        
        # 로깅 레벨 설정
        logging.getLogger().setLevel(getattr(logging, config.log_level.upper()))
        
        logger.info("=== 허깅페이스 gRPC 서버 시작 ===")
        logger.info(f"STT 모델: {config.model.stt_model_name}")
        logger.info(f"TTS 모델: {config.model.tts_model_name}")
        logger.info(f"디바이스: {config.model.device}")
        logger.info(f"서버 주소: {config.server.host}:{config.server.port}")
        
        # 서버 시작
        server = GRPCServer(config)
        server.start()
        
    except KeyboardInterrupt:
        logger.info("사용자 인터럽트로 서버 종료")
    except Exception as e:
        logger.error(f"서버 실행 중 오류: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()