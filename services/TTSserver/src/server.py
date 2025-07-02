# services/TTSserver/src/server.py
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

from models.tts_model import TTSModel
from configs.env import AppConfig
from audio_processor import AudioProcessor

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AudioProcessingServicer(audio_service_pb2_grpc.AudioProcessingServicer):
    """gRPC 오디오 처리 서비스 (XTTS-v2 + proto 매칭)"""
    
    def __init__(self, config: AppConfig):
        self.config = config
        self.tts_model = None
        self.audio_processor = AudioProcessor()
        self._initialize_models()
    
    def _initialize_models(self) -> None:
        """모델 초기화"""
        try:
            logger.info("XTTS-v2 TTS 모델 초기화 시작")
            
            # TTS 모델 초기화
            self.tts_model = TTSModel(
                model_name=self.config.model.tts_model_name,
                device=self.config.model.device,
                cache_dir=self.config.model.cache_dir
            )
            self.tts_model.load_model()
            
            logger.info("XTTS-v2 TTS 모델 초기화 완료")
            
        except Exception as e:
            logger.error(f"TTS 모델 초기화 실패: {e}")
            raise
    
    def ProcessSTT(self, request, context):
        """STT 처리 (미구현)"""
        logger.warning(f"⚠️ STT 기능은 구현되지 않음: {request.request_id}")
        context.set_code(grpc.StatusCode.UNIMPLEMENTED)
        context.set_details("STT 기능은 구현되지 않았습니다")
        return audio_service_pb2.STTResponse(
            request_id=request.request_id,
            error="STT 기능은 구현되지 않았습니다"
        )
    
    def ProcessTTS(self, request, context):
        """TTS 처리 (proto 파일 매칭)"""
        try:
            logger.info(f"🔊 TTS 요청 처리 시작: {request.request_id}")
            start_time = time.time()
            
            # 입력 텍스트 검증
            if not request.text or not request.text.strip():
                logger.warning(f"⚠️ 빈 텍스트 입력: {request.request_id}")
                return audio_service_pb2.TTSResponse(
                    request_id=request.request_id,
                    error="입력 텍스트가 비어있습니다"
                )
            
            # 텍스트 길이 검증
            max_length = getattr(self.config.model, 'max_text_length', 1000)
            if not self.audio_processor.validate_text_length(request.text, max_length):
                logger.warning(f"⚠️ 텍스트가 너무 김 ({len(request.text)}글자): {request.request_id}")
                return audio_service_pb2.TTSResponse(
                    request_id=request.request_id,
                    error=f"텍스트가 너무 깁니다 (최대 {max_length}글자)"
                )
            
            # proto 파일에서 설정값 추출
            config = request.config
            voice = getattr(config, 'voice', 'female')
            language = getattr(config, 'language', 'korean')
            speed = getattr(config, 'speed', 1.0)
            pitch = getattr(config, 'pitch', 1.0)
            
            logger.info(f"🎯 TTS 설정: voice={voice}, language={language}, speed={speed}, pitch={pitch}")
            
            # 텍스트 전처리
            cleaned_text = self.audio_processor.clean_text(request.text)
            
            # 긴 텍스트 분할 처리
            if len(cleaned_text) > 200:
                text_chunks = self.audio_processor.split_long_text(cleaned_text, 200)
                audio_chunks = []
                
                for i, chunk in enumerate(text_chunks):
                    logger.info(f"청크 {i+1}/{len(text_chunks)} 처리 중...")
                    chunk_result = self.tts_model.process(
                        text=chunk,
                        speaker=voice,
                        language=self._map_language(language)
                    )
                    audio_chunks.append(chunk_result["audio_array"])
                
                # 오디오 청크들 연결
                final_audio = self.audio_processor.concatenate_audio_chunks(
                    audio_chunks, 
                    silence_duration=0.3,
                    sample_rate=self.tts_model.sample_rate
                )
                
                # 최종 WAV 변환
                audio_bytes = self.audio_processor.convert_to_wav_bytes(
                    final_audio, self.tts_model.sample_rate
                )
                
                processing_time = (time.time() - start_time) * 1000
                audio_duration = len(final_audio) / self.tts_model.sample_rate * 1000
                
            else:
                # 단일 청크 처리
                result = self.tts_model.process(
                    text=cleaned_text,
                    speaker=voice,
                    language=self._map_language(language)
                )
                
                # 오디오 후처리
                processed_audio = self.audio_processor.normalize_audio_output(
                    result["audio_array"]
                )
                
                # WAV 형식으로 변환 (이미 XTTS-v2에서 WAV로 나오지만 후처리용)
                audio_bytes = result.get("audio_data") or self.audio_processor.convert_to_wav_bytes(
                    processed_audio, result["sample_rate"]
                )
                
                processing_time = result["processing_time_ms"]
                audio_duration = result["audio_duration_ms"]
            
            # 응답 생성
            response = audio_service_pb2.TTSResponse(
                request_id=request.request_id,
                audio_data=audio_bytes,
                format=audio_service_pb2.WAV,
                stats=audio_service_pb2.ProcessingStats(
                    processing_time_ms=int(processing_time),
                    model_used=self.tts_model.model_name,
                    timestamp=int(time.time()),
                    audio_duration_ms=int(audio_duration)
                )
            )
            
            logger.info(f"✅ TTS 요청 처리 완료: {request.request_id}")
            logger.info(f"🔊 TTS 결과: {len(cleaned_text)}글자 → {audio_duration:.1f}ms 오디오 (처리시간: {processing_time:.1f}ms)")
            
            return response
            
        except Exception as e:
            logger.error(f"❌ TTS 처리 중 오류 ({request.request_id}): {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"TTS 처리 실패: {str(e)}")
            return audio_service_pb2.TTSResponse(
                request_id=request.request_id,
                error=str(e)
            )
    
    def _map_language(self, language: str) -> str:
        """proto 언어를 XTTS-v2 언어로 매핑"""
        language_map = {
            "korean": "ko",
            "ko": "ko",
            "english": "en", 
            "en": "en",
            "japanese": "ja",
            "ja": "ja",
            "chinese": "zh",
            "zh": "zh"
        }
        return language_map.get(language.lower(), "ko")
    
    def HealthCheck(self, request, context):
        """헬스 체크"""
        try:
            logger.debug(f"🔍 헬스 체크 요청: {request.service}")
            
            # TTS 모델 상태 확인
            tts_available = self.tts_model.is_loaded() if self.tts_model else False
            stt_available = False  # STT는 구현 안됨
            
            # 서비스별 상태
            services = {}
            
            if request.service in ["tts", "all"]:
                services["tts"] = audio_service_pb2.ServiceHealth(
                    available=tts_available,
                    model_name=self.config.model.tts_model_name,
                    version="1.0",
                    uptime_seconds=int(time.time())
                )
            
            if request.service in ["stt", "all"]:
                services["stt"] = audio_service_pb2.ServiceHealth(
                    available=stt_available,
                    model_name="not_implemented",
                    version="0.0",
                    uptime_seconds=0
                )
            
            # 전체 서비스 상태 결정
            if request.service == "tts":
                status = audio_service_pb2.SERVING if tts_available else audio_service_pb2.NOT_SERVING
            elif request.service == "stt":
                status = audio_service_pb2.NOT_SERVING  # STT 미구현
            else:  # "all" 또는 기타
                status = audio_service_pb2.SERVING if tts_available else audio_service_pb2.NOT_SERVING
            
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
            logger.info("🚀 XTTS-v2 TTS gRPC 서버 시작")
            
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
            logger.info(f"✅ XTTS-v2 TTS gRPC 서버가 {listen_addr}에서 시작되었습니다")
            
            # 종료 시그널 핸들러 등록
            signal.signal(signal.SIGTERM, self._signal_handler)
            signal.signal(signal.SIGINT, self._signal_handler)
            
            # 서버 대기
            self.server.wait_for_termination()
            
        except Exception as e:
            logger.error(f"❌ TTS 서버 시작 실패: {e}")
            raise
    
    def _signal_handler(self, signum, frame):
        """종료 시그널 핸들러"""
        logger.info(f"🔄 종료 시그널 수신: {signum}")
        self.stop()
    
    def stop(self, grace_period: int = 30):
        """서버 정지"""
        if self.server:
            logger.info("🔄 XTTS-v2 TTS gRPC 서버 정지 중...")
            self.server.stop(grace_period)
            logger.info("✅ XTTS-v2 TTS gRPC 서버 정지 완료")

def main():
    """메인 함수"""
    try:
        # 설정 로드
        config = AppConfig.from_env()
        
        # 로깅 레벨 설정
        logging.getLogger().setLevel(getattr(logging, config.log_level.upper()))
        
        logger.info("=== 🔊 XTTS-v2 TTS gRPC 서버 시작 ===")
        logger.info(f"TTS 모델: {config.model.tts_model_name}")
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