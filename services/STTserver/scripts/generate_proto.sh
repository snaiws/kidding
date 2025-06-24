#!/bin/bash

# 프로토콜 버퍼 컴파일 스크립트

set -e

echo "=== 프로토콜 버퍼 컴파일 시작 ==="

# 출력 디렉토리 생성
mkdir -p src/

# protoc 실행
python -m grpc_tools.protoc \
    --python_out=./src/ \
    --grpc_python_out=./src/ \
    --proto_path=./proto/ \
    ./proto/audio_service.proto

echo "프로토콜 버퍼 컴파일 완료"
echo "생성된 파일:"
echo "  - src/audio_service_pb2.py"
echo "  - src/audio_service_pb2_grpc.py"

# Python 경로 수정 (상대 import 문제 해결)
sed -i 's/import audio_service_pb2/from . import audio_service_pb2/g' src/audio_service_pb2_grpc.py

echo "=== 프로토콜 버퍼 컴파일 완료 ==="