
import torch
import torchaudio
import numpy as np
from transformers import WhisperProcessor, WhisperForConditionalGeneration
from typing import Dict, Any, Union
import logging
import time

from .base_model import BaseModel

logger = logging.getLogger(__name__)

class STTModel(BaseModel):
    """Speech-to-Text 모델"""
    
    def __init__(self, model_name: str, device: str, cache_dir: str):
        super().__init__(model_name, device, cache_dir)
        self.sample_rate = 16000
    
    def load_model(self) -> None:
        """Whisper 모델 로드"""
        try:
            logger.info(f"STT 모델 로딩 시작: {self.model_name}")
            start_time = time.time()
            
            self.processor = WhisperProcessor.from_pretrained(
                self.model_name,
                cache_dir=self.cache_dir
            )
            
            self.model = WhisperForConditionalGeneration.from_pretrained(
                self.model_name,
                cache_dir=self.cache_dir,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                low_cpu_mem_usage=True
            )
            
            self.model.to(self.device)
            self.model.eval()
            
            # 모델 워밍업
            self._warmup_model()
            
            self._is_loaded = True
            load_time = time.time() - start_time
            logger.info(f"STT 모델 로딩 완료: {load_time:.2f}초")
            
        except Exception as e:
            logger.error(f"STT 모델 로딩 실패: {e}")
            raise
    
    def _warmup_model(self) -> None:
        """모델 워밍업"""
        try:
            # 더미 오디오로 추론 한 번 실행
            dummy_audio = torch.randn(1, self.sample_rate * 2).to(self.device)
            with torch.no_grad():
                input_features = self.processor(
                    dummy_audio.cpu().numpy().squeeze(),
                    sampling_rate=self.sample_rate,
                    return_tensors="pt"
                ).input_features.to(self.device)
                
                self.model.generate(input_features, max_length=50)
            
            logger.info("STT 모델 워밍업 완료")
        except Exception as e:
            logger.warning(f"STT 모델 워밍업 실패: {e}")
            
    def process(self, audio_data: Union[bytes, np.ndarray], language: str = "korean", **kwargs) -> Dict[str, Any]:
        """음성을 텍스트로 변환"""
        if not self._is_loaded:
            raise RuntimeError("모델이 로드되지 않았습니다")
        
        start_time = time.time()
        
        try:
            # 오디오 데이터 전처리
            if isinstance(audio_data, bytes):
                audio_array = np.frombuffer(audio_data, dtype=np.float32)
            else:
                audio_array = audio_data
            
            # 샘플링 레이트 맞추기
            if len(audio_array.shape) > 1:
                audio_array = audio_array.mean(axis=1)  # 스테레오를 모노로
            
            # 입력 특성 추출
            input_features = self.processor(
                audio_array,
                sampling_rate=self.sample_rate,
                return_tensors="pt"
            ).input_features.to(self.device)
            
            # 🔧 핵심 수정: 모델의 데이터 타입에 맞춰 입력 변환
            if self.model.dtype == torch.float16:
                input_features = input_features.half()
                logger.debug("입력을 float16으로 변환")
            elif self.model.dtype == torch.float32:
                input_features = input_features.float()
                logger.debug("입력을 float32로 변환")
            
            logger.info(f"모델 dtype: {self.model.dtype}, 입력 dtype: {input_features.dtype}")
            
            # 언어 토큰 설정
            forced_decoder_ids = self.processor.get_decoder_prompt_ids(
                language=language, 
                task="transcribe"
            )
            
            # 추론 실행
            with torch.no_grad():
                predicted_ids = self.model.generate(
                    input_features,
                    forced_decoder_ids=forced_decoder_ids,
                    max_length=448,
                    return_timestamps=True
                )
            
            # 결과 디코딩
            transcription = self.processor.batch_decode(
                predicted_ids, 
                skip_special_tokens=True
            )[0]
            
            processing_time = (time.time() - start_time) * 1000
            
            logger.info(f"STT 처리 완료: '{transcription}' ({processing_time:.1f}ms)")
            
            return {
                "transcription": transcription.strip(),
                "confidence": 0.95,  # Whisper는 confidence score를 직접 제공하지 않음
                "processing_time_ms": processing_time,
                "model_used": self.model_name,
                "audio_length_ms": len(audio_array) / self.sample_rate * 1000
            }
            
        except Exception as e:
            logger.error(f"STT 처리 중 오류: {e}")
            raise