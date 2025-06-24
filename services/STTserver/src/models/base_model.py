
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging
import time
import torch

logger = logging.getLogger(__name__)

class BaseModel(ABC):
    """모델 기본 클래스"""
    
    def __init__(self, model_name: str, device: str, cache_dir: str):
        self.model_name = model_name
        self.device = device
        self.cache_dir = cache_dir
        self.model = None
        self.processor = None
        self._is_loaded = False
    
    @abstractmethod
    def load_model(self) -> None:
        """모델 로드"""
        pass
    
    @abstractmethod
    def process(self, input_data: Any, **kwargs) -> Dict[str, Any]:
        """모델 추론"""
        pass
    
    def is_loaded(self) -> bool:
        """모델 로드 상태 확인"""
        return self._is_loaded
    
    def get_model_info(self) -> Dict[str, str]:
        """모델 정보 반환"""
        return {
            "model_name": self.model_name,
            "device": self.device,
            "status": "loaded" if self._is_loaded else "not_loaded"
        }