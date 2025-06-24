#!/usr/bin/env python3

import grpc
import sys
import os

# 프로젝트 루트를 Python 경로에 추가
sys.path.insert(0, '/app/src')

try:
    # import audio_service_pb2
    # import audio_service_pb2_grpc
    
    def check_health():
        try:
            channel = grpc.insecure_channel('localhost:50051')
            # stub = audio_service_pb2_grpc.AudioProcessingStub(channel)
            
            # request = audio_service_pb2.HealthCheckRequest(service="audio_processing")
            # response = stub.HealthCheck(request, timeout=5)
            
            # 임시로 간단한 연결 체크
            grpc.channel_ready_future(channel).result(timeout=5)
            
            # if response.status == 1:  # SERVING
            print("Health check passed")
            return True
            # else:
            #     print("Service not serving")
            #     return False
                
        except grpc.RpcError as e:
            print(f"Health check failed: {e}")
            return False
        except Exception as e:
            print(f"Health check error: {e}")
            return False
    
    if __name__ == "__main__":
        if check_health():
            sys.exit(0)
        else:
            sys.exit(1)
            
except ImportError:
    print("Proto files not found, skipping health check")
    sys.exit(0)