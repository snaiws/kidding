
#!/usr/bin/env python3

import os
import sys
import subprocess
import time

def download_models():
    '''모델 사전 다운로드'''
    print("=== 모델 다운로드 시작 ===")
    
    from transformers import WhisperProcessor, WhisperForConditionalGeneration
    from transformers import SpeechT5Processor, SpeechT5ForTextToSpeech, SpeechT5HifiGan
    from datasets import load_dataset
    
    cache_dir = os.environ.get("MODEL_CACHE_DIR", "/app/models")
    
    try:
        # STT 모델 다운로드
        stt_model = os.environ.get("STT_MODEL", "openai/whisper-large-v3")
        print(f"STT 모델 다운로드: {stt_model}")
        WhisperProcessor.from_pretrained(stt_model, cache_dir=cache_dir)
        WhisperForConditionalGeneration.from_pretrained(stt_model, cache_dir=cache_dir)
        
        # TTS 모델 다운로드
        tts_model = os.environ.get("TTS_MODEL", "microsoft/speecht5_tts")
        print(f"TTS 모델 다운로드: {tts_model}")
        SpeechT5Processor.from_pretrained(tts_model, cache_dir=cache_dir)
        SpeechT5ForTextToSpeech.from_pretrained(tts_model, cache_dir=cache_dir)
        
        # 보코더 다운로드
        print("보코더 다운로드: microsoft/speecht5_hifigan")
        SpeechT5HifiGan.from_pretrained("microsoft/speecht5_hifigan", cache_dir=cache_dir)
        
        # 스피커 임베딩 다운로드
        print("스피커 임베딩 다운로드")
        load_dataset("Matthijs/cmu-arctic-xvectors", split="validation", cache_dir=cache_dir)
        
        print("=== 모델 다운로드 완료 ===")
        
    except Exception as e:
        print(f"모델 다운로드 실패: {e}")
        return False
    
    return True

def main():
    print("=== 허깅페이스 gRPC 서버 시작 스크립트 ===")
    
    # 환경 변수 출력
    print("환경 설정:")
    print(f"  USE_GPU: {os.environ.get('USE_GPU', 'false')}")
    print(f"  DEVICE: {os.environ.get('DEVICE', 'cpu')}")
    print(f"  STT_MODEL: {os.environ.get('STT_MODEL', 'openai/whisper-large-v3')}")
    print(f"  TTS_MODEL: {os.environ.get('TTS_MODEL', 'microsoft/speecht5_tts')}")
    print(f"  GRPC_PORT: {os.environ.get('GRPC_PORT', '50051')}")
    print(f"  MAX_WORKERS: {os.environ.get('MAX_WORKERS', '4')}")
    
    # 모델 사전 다운로드
    if not download_models():
        print("모델 다운로드 실패로 서버 시작 중단")
        sys.exit(1)
    
    # 잠시 대기
    print("서버 시작 준비 중...")
    time.sleep(2)
    
    # 서버 시작
    print("=== gRPC 서버 시작 ===")
    try:
        os.chdir("/app/src")
        subprocess.run([sys.executable, "server.py"], check=True)
    except KeyboardInterrupt:
        print("사용자 인터럽트로 서버 종료")
    except subprocess.CalledProcessError as e:
        print(f"서버 실행 실패: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()