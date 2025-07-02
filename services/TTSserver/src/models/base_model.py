# services/TTSserver/src/models/base_model.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Union
import logging

logger = logging.getLogger(__name__)

class BaseModel(ABC):
    """기본 모델 추상 클래스"""
    
    def __init__(self, model_name: str, device: str, cache_dir: str):
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self.model = None
        self.processor = None
        self._is_loaded = False
        
        logger.info(f"모델 초기화: {model_name}, 디바이스: {device}")
    
    @abstractmethod
    def load_model(self) -> None:
        """모델을 로드합니다"""
        pass
    
    @abstractmethod
    def process(self, **kwargs) -> Dict[str, Any]:
        """입력을 처리합니다"""
        pass
    
    def is_loaded(self) -> bool:
        """모델이 로드되었는지 확인"""
        return self._is_loaded
    
    def unload_model(self) -> None:
        """모델을 메모리에서 해제"""
        try:
            if self.model is not None:
                del self.model
                self.model = None
            
            if self.processor is not None:
                del self.processor
                self.processor = None
            
            self._is_loaded = False
            logger.info(f"모델 해제 완료: {self.model_name}")
            
        except Exception as e:
            logger.error(f"모델 해제 실패: {e}")
    
    def get_model_info(self) -> Dict[str, Any]:
        """모델 정보 반환"""
        return {
            "model_name": self.model_name,
            "device": self.device,
            "cache_dir": self.cache_dir,
            "is_loaded": self._is_loaded
        }