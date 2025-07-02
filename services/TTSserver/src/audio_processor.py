# services/TTSserver/src/audio_processor.py
import numpy as np
import librosa
import soundfile as sf
import io
from typing import Tuple, Union, Optional
import logging

logger = logging.getLogger(__name__)

class AudioProcessor:
    """TTS용 오디오 처리 유틸리티"""
    
    @staticmethod
    def clean_text(text: str) -> str:
        """XTTS-v2를 위한 텍스트 정리"""
        try:
            # 기본적인 텍스트 정리
            cleaned = text.strip()
            
            # 연속된 공백 제거
            import re
            cleaned = re.sub(r'\s+', ' ', cleaned)
            
            # XTTS-v2는 특수문자를 잘 처리하므로 최소한만 변환
            replacements = {
                '&': '그리고',
                '@': '골뱅이',
                '#': '샵',
                '$': '달러',
                '€': '유로',
                '£': '파운드',
                '¥': '엔',
                '₩': '원'
            }
            
            for symbol, replacement in replacements.items():
                cleaned = cleaned.replace(symbol, replacement)
            
            logger.debug(f"텍스트 정리 완료: '{text}' → '{cleaned}'")
            return cleaned
            
        except Exception as e:
            logger.error(f"텍스트 정리 실패: {e}")
            return text
    
    @staticmethod
    def validate_text_length(text: str, max_length: int = 1000) -> bool:
        """텍스트 길이 검증"""
        return len(text.strip()) <= max_length
    
    @staticmethod
    def split_long_text(text: str, max_length: int = 200) -> list:
        """긴 텍스트를 문장 단위로 분할"""
        try:
            import re
            
            # 문장 구분자로 분할
            sentences = re.split(r'[.!?]\s+', text)
            
            chunks = []
            current_chunk = ""
            
            for sentence in sentences:
                if len(current_chunk + sentence) <= max_length:
                    current_chunk += sentence + ". "
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + ". "
            
            if current_chunk:
                chunks.append(current_chunk.strip())
            
            logger.info(f"텍스트 분할: {len(text)}글자 → {len(chunks)}개 청크")
            return chunks
            
        except Exception as e:
            logger.error(f"텍스트 분할 실패: {e}")
            return [text]
    
    @staticmethod
    def normalize_audio_output(audio: np.ndarray) -> np.ndarray:
        """생성된 오디오 후처리"""
        try:
            # NaN, Inf 값 제거
            audio = np.nan_to_num(audio, nan=0.0, posinf=1.0, neginf=-1.0)
            
            # 클리핑 방지
            audio = np.clip(audio, -1.0, 1.0)
            
            # 볼륨 정규화 (너무 작은 신호 증폭)
            max_amplitude = np.abs(audio).max()
            if max_amplitude > 0 and max_amplitude < 0.1:
                audio = audio / max_amplitude * 0.7
            
            logger.debug(f"오디오 후처리 완료: 범위=[{audio.min():.3f}, {audio.max():.3f}]")
            return audio
            
        except Exception as e:
            logger.error(f"오디오 후처리 실패: {e}")
            return audio
    
    @staticmethod
    def concatenate_audio_chunks(audio_chunks: list, 
                               silence_duration: float = 0.5,
                               sample_rate: int = 16000) -> np.ndarray:
        """여러 오디오 청크를 묵음과 함께 연결"""
        try:
            if not audio_chunks:
                return np.array([])
            
            if len(audio_chunks) == 1:
                return audio_chunks[0]
            
            # 묵음 생성
            silence_samples = int(silence_duration * sample_rate)
            silence = np.zeros(silence_samples)
            
            # 청크들 연결
            result = audio_chunks[0]
            for chunk in audio_chunks[1:]:
                result = np.concatenate([result, silence, chunk])
            
            logger.info(f"오디오 청크 연결 완료: {len(audio_chunks)}개 → {len(result)}샘플")
            return result
            
        except Exception as e:
            logger.error(f"오디오 청크 연결 실패: {e}")
            return np.concatenate(audio_chunks) if audio_chunks else np.array([])
    
    @staticmethod
    def convert_to_wav_bytes(audio: np.ndarray, sample_rate: int = 16000) -> bytes:
        """numpy 배열을 WAV 바이트로 변환"""
        try:
            # 16-bit PCM으로 변환
            audio_int16 = (audio * 32767).astype(np.int16)
            
            # BytesIO 버퍼 사용
            buffer = io.BytesIO()
            sf.write(buffer, audio_int16, sample_rate, format='WAV', subtype='PCM_16')
            
            # 바이트 데이터 반환
            buffer.seek(0)
            wav_bytes = buffer.read()
            
            logger.debug(f"WAV 변환 완료: {len(audio)}샘플 → {len(wav_bytes)}바이트")
            return wav_bytes
            
        except Exception as e:
            logger.error(f"WAV 변환 실패: {e}")
            # 대체 방법: 간단한 PCM 바이트 반환
            audio_int16 = (audio * 32767).astype(np.int16)
            return audio_int16.tobytes()