
import numpy as np
import librosa
import soundfile as sf
import io
from typing import Tuple, Union
import logging

logger = logging.getLogger(__name__)

class AudioProcessor:
    """오디오 처리 유틸리티"""
    
    @staticmethod
    def load_audio_from_bytes(audio_bytes: bytes, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
        """바이트에서 오디오 로드 및 리샘플링"""
        try:
            # BytesIO로 변환
            audio_buffer = io.BytesIO(audio_bytes)
            
            # librosa로 로드
            audio, sr = librosa.load(audio_buffer, sr=target_sr, mono=True)
            
            return audio, sr
            
        except Exception as e:
            logger.error(f"오디오 로드 실패: {e}")
            raise
    
    @staticmethod
    def normalize_audio(audio: np.ndarray) -> np.ndarray:
        """오디오 정규화"""
        try:
            # RMS 정규화
            rms = np.sqrt(np.mean(audio**2))
            if rms > 0:
                audio = audio / rms * 0.1
            
            # 클리핑 방지
            audio = np.clip(audio, -1.0, 1.0)
            
            return audio
            
        except Exception as e:
            logger.error(f"오디오 정규화 실패: {e}")
            return audio
    
    @staticmethod
    def detect_speech_activity(audio: np.ndarray, sr: int = 16000, 
                             frame_length: int = 2048, hop_length: int = 512) -> bool:
        """간단한 음성 활동 감지"""
        try:
            # 에너지 기반 VAD
            energy = librosa.feature.rms(
                y=audio, 
                frame_length=frame_length, 
                hop_length=hop_length
            )[0]
            
            # 임계값 기반 판단
            energy_threshold = np.mean(energy) + 2 * np.std(energy)
            speech_frames = np.sum(energy > energy_threshold)
            
            # 전체 프레임의 10% 이상이 음성이면 True
            return speech_frames / len(energy) > 0.1
            
        except Exception as e:
            logger.warning(f"VAD 처리 실패: {e}")
            return True  # 실패시 음성 있다고 가정