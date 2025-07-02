# services/TTSserver/src/models/tts_model.py
import torch
import torchaudio
import numpy as np
from transformers import AutoTokenizer, AutoModel, pipeline
from typing import Dict, Any, Union, Optional
import logging
import time
import io

from .base_model import BaseModel

logger = logging.getLogger(__name__)

class TTSModel(BaseModel):
    """허깅페이스 Bark TTS 모델"""
    
    def __init__(self, model_name: str, device: str, cache_dir: str):
        super().__init__(model_name, device, cache_dir)
        self.sample_rate = 24000  # Bark 기본 샘플링 레이트
        self.tts_pipeline = None
        
    def load_model(self) -> None:
        """허깅페이스에서 Bark 모델 로드"""
        try:
            logger.info(f"허깅페이스 Bark 모델 로딩 시작: {self.model_name}")
            start_time = time.time()
            
            # 허깅페이스 TTS 파이프라인 생성 (cache_dir 제거)
            self.tts_pipeline = pipeline(
                "text-to-speech",
                model=self.model_name,
                device=0 if self.device == "cuda" else -1,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32
            )
            
            # 모델 워밍업
            self._warmup_model()
            
            self._is_loaded = True
            load_time = time.time() - start_time
            logger.info(f"허깅페이스 Bark 모델 로딩 완료: {load_time:.2f}초")
            
        except Exception as e:
            logger.error(f"허깅페이스 Bark 모델 로딩 실패: {e}")
            raise
    
    def _warmup_model(self) -> None:
        """모델 워밍업"""
        try:
            logger.info("Bark 모델 워밍업 시작...")
            
            # 더미 텍스트로 추론 한 번 실행
            dummy_text = "Hello, this is a test."
            result = self.tts_pipeline(dummy_text)
            
            logger.info("Bark 모델 워밍업 완료")
            
        except Exception as e:
            logger.warning(f"XTTS-v2 모델 워밍업 실패: {e}")
            
    def process(self, text: str, speaker: Optional[str] = None, language: str = "ko", **kwargs) -> Dict[str, Any]:
        """텍스트를 음성으로 변환"""
        if not self._is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다")
        
        if not text or not text.strip():
            raise ValueError("입력 텍스트가 비어있습니다")
        
        start_time = time.time()
        
        try:
            logger.info(f"Bark TTS 처리 시작: '{text[:50]}{'...' if len(text) > 50 else ''}'")
            
            # 허깅페이스 파이프라인으로 음성 생성
            result = self.tts_pipeline(text.strip())
            
            # 결과에서 오디오 데이터 추출
            if isinstance(result, dict):
                audio_array = result["audio"]
                sample_rate = result.get("sampling_rate", self.sample_rate)
            else:
                # 리스트나 다른 형태일 경우
                audio_array = result
                sample_rate = self.sample_rate
            
            # numpy 배열로 변환
            if isinstance(audio_array, torch.Tensor):
                audio_numpy = audio_array.cpu().numpy()
            else:
                audio_numpy = np.array(audio_array)
            
            # 모노로 변환 (필요한 경우)
            if len(audio_numpy.shape) > 1:
                audio_numpy = audio_numpy.mean(axis=0)
            
            # 정규화
            if audio_numpy.max() > 1.0 or audio_numpy.min() < -1.0:
                audio_numpy = audio_numpy / np.abs(audio_numpy).max()
            
            # WAV 바이트로 변환
            audio_bytes = self.audio_to_wav_bytes(audio_numpy, sample_rate)
            
            processing_time = (time.time() - start_time) * 1000
            audio_duration = len(audio_numpy) / sample_rate * 1000
            
            logger.info(f"Bark TTS 처리 완료: {len(text)}글자 → {audio_duration:.1f}ms 오디오 ({processing_time:.1f}ms)")
            
            return {
                "audio_data": audio_bytes,
                "audio_array": audio_numpy,
                "sample_rate": sample_rate,
                "text_length": len(text),
                "audio_duration_ms": audio_duration,
                "processing_time_ms": processing_time,
                "model_used": self.model_name,
                "speaker": speaker,
                "language": language
            }
            
        except Exception as e:
            logger.error(f"Bark TTS 처리 중 오류: {e}")
            raise
    
    def audio_to_wav_bytes(self, audio_array: np.ndarray, sample_rate: int = None) -> bytes:
        """numpy 배열을 WAV 바이트로 변환"""
        if sample_rate is None:
            sample_rate = self.sample_rate
            
        try:
            # BytesIO 버퍼 생성
            buffer = io.BytesIO()
            
            # 16-bit PCM으로 변환
            audio_int16 = (audio_array * 32767).astype(np.int16)
            
            # WAV 파일로 저장
            torchaudio.save(
                buffer,
                torch.from_numpy(audio_int16).unsqueeze(0).float() / 32767.0,
                sample_rate,
                format="wav"
            )
            
            # 바이트 데이터 반환
            buffer.seek(0)
            return buffer.read()
            
        except Exception as e:
            logger.error(f"WAV 변환 실패: {e}")
            # 대체 방법: 간단한 PCM 바이트 반환
            audio_int16 = (audio_array * 32767).astype(np.int16)
            return audio_int16.tobytes()
    
    def get_available_speakers(self) -> list:
        """사용 가능한 화자 목록 반환"""
        # Bark 모델의 기본 화자들
        return ["female", "male"]
    
    def get_available_languages(self) -> list:
        """사용 가능한 언어 목록 반환"""
        # Bark 지원 언어들
        return ["ko", "en", "ja", "zh", "de", "fr", "es", "it", "pt", "hi", "ru"]