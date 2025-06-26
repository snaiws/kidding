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
        """바이트에서 오디오 로드 및 리샘플링 (Raw PCM 및 파일 포맷 지원)"""
        try:
            # 먼저 파일 포맷으로 시도 (WAV, MP3, FLAC 등)
            audio_buffer = io.BytesIO(audio_bytes)
            try:
                audio, sr = librosa.load(audio_buffer, sr=target_sr, mono=True)
                logger.info(f"파일 포맷으로 오디오 로드 성공: {len(audio)} samples, {sr}Hz")
                return audio, sr
            except Exception as file_error:
                logger.info(f"파일 포맷 로드 실패, Raw PCM으로 시도: {file_error}")
                
                # Raw PCM 데이터로 처리
                return AudioProcessor._load_raw_pcm(audio_bytes, target_sr)
                
        except Exception as e:
            logger.error(f"오디오 로드 완전 실패: {e}")
            raise
    
    @staticmethod
    def _load_raw_pcm(audio_bytes: bytes, target_sr: int = 16000) -> Tuple[np.ndarray, int]:
        """Raw PCM 데이터 처리"""
        try:
            # 16-bit little-endian PCM으로 가정
            pcm_array = np.frombuffer(audio_bytes, dtype=np.int16)
            
            if len(pcm_array) == 0:
                raise ValueError("PCM 데이터가 비어있습니다")
            
            # int16을 float32로 정규화 (-1.0 ~ 1.0)
            audio = pcm_array.astype(np.float32) / 32768.0
            
            # 클리핑 방지
            audio = np.clip(audio, -1.0, 1.0)
            
            logger.info(f"Raw PCM 로드 성공: {len(audio)} samples, {target_sr}Hz, 범위: [{audio.min():.3f}, {audio.max():.3f}]")
            
            return audio, target_sr
            
        except Exception as e:
            logger.error(f"Raw PCM 처리 실패: {e}")
            raise ValueError(f"Raw PCM 데이터 처리 실패: {e}")
    
    @staticmethod
    def normalize_audio(audio: np.ndarray) -> np.ndarray:
        """오디오 정규화"""
        try:
            # 이미 정규화된 경우 추가 정규화 스킵
            if np.abs(audio).max() <= 1.0:
                # RMS 정규화 (너무 작은 신호 증폭)
                rms = np.sqrt(np.mean(audio**2))
                if rms > 0 and rms < 0.01:  # 매우 작은 신호만 증폭
                    audio = audio / rms * 0.1
            
            # 최종 클리핑
            audio = np.clip(audio, -1.0, 1.0)
            
            logger.debug(f"오디오 정규화 완료: RMS={np.sqrt(np.mean(audio**2)):.4f}, 범위=[{audio.min():.3f}, {audio.max():.3f}]")
            
            return audio
            
        except Exception as e:
            logger.error(f"오디오 정규화 실패: {e}")
            return audio
    
    @staticmethod
    def detect_speech_activity(audio: np.ndarray, sr: int = 16000, 
                             frame_length: int = 2048, hop_length: int = 512) -> bool:
        """VAD 비활성화 - Whisper가 알아서 처리"""
        return True  # 항상 처리하도록