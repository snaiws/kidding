# services/webserver/src/routes/websocket.py (proto 파일 매칭 버전)
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
from typing import Dict, Optional
import io
import wave
import logging

# gRPC 클라이언트 임포트 (수정된 버전)
from .grpc_client import get_stt_client, get_tts_client, cleanup_grpc_clients

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter()

class Session:
    def __init__(self, session_id: int, websocket: WebSocket):
        self.session_id = session_id
        self.websocket = websocket
        self.status = 'connected'  # connected, recording, paused, processing, converting, playing, completed
        self.audio_buffer = []
        self.created_at = asyncio.get_event_loop().time()
        self.last_audio_time = None
        
    def add_audio_data(self, data: bytes):
        self.audio_buffer.append(data)
        self.last_audio_time = asyncio.get_event_loop().time()
        
    def get_combined_audio(self) -> bytes:
        return b''.join(self.audio_buffer)
        
    def clear_audio_buffer(self):
        self.audio_buffer.clear()

class ConnectionManager:
    def __init__(self):
        self.sessions: Dict[int, Session] = {}
        self.status_connections: Dict[str, WebSocket] = {}
        
    async def connect_audio_session(self, websocket: WebSocket, session_id: int) -> Session:
        await websocket.accept()
        session = Session(session_id, websocket)
        self.sessions[session_id] = session
        logger.info(f"✅ 오디오 세션 연결: {session_id} (총 {len(self.sessions)}개 세션)")
        return session
        
    async def connect_status(self, websocket: WebSocket) -> str:
        await websocket.accept()
        connection_id = f"status_{len(self.status_connections)}"
        self.status_connections[connection_id] = websocket
        logger.info(f"✅ 상태 연결: {connection_id}")
        return connection_id
        
    def disconnect_session(self, session_id: int):
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"❌ 세션 연결 해제: {session_id} (총 {len(self.sessions)}개 세션)")
            
    def disconnect_status(self, connection_id: str):
        if connection_id in self.status_connections:
            del self.status_connections[connection_id]
            logger.info(f"❌ 상태 연결 해제: {connection_id}")
            
    def get_session(self, session_id: int) -> Optional[Session]:
        return self.sessions.get(session_id)
        
    def get_session_count(self) -> int:
        return len(self.sessions)

manager = ConnectionManager()

@router.websocket("/audio")
async def websocket_audio(websocket: WebSocket):
    """실시간 음성 데이터 처리 (STT→TTS 파이프라인)"""
    session: Optional[Session] = None
    session_id = None
    
    try:
        # 초기 연결 수락
        await websocket.accept()
        logger.info("🔗 WebSocket 연결 수락됨")
        
        # 세션 시작 메시지 대기
        while True:
            try:
                message = await websocket.receive()
                
                if message.get('type') == 'websocket.disconnect':
                    logger.info(f"🔌 클라이언트 연결 종료")
                    return
                
                if 'text' in message:
                    try:
                        data = json.loads(message['text'])
                    except json.JSONDecodeError as je:
                        logger.error(f"❌ JSON 파싱 실패: {je}")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": f"JSON 파싱 실패: {je}"
                        }))
                        continue
                    
                    message_type = data.get('type')
                    
                    if message_type == 'session_start':
                        session_id = data.get('session_id')
                        
                        if session_id is None:
                            logger.error("❌ session_id가 제공되지 않음")
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "message": "session_id가 필요합니다"
                            }))
                            continue
                        
                        # 기존 세션 중복 체크
                        if session_id in manager.sessions:
                            logger.warning(f"⚠️ 중복된 세션 ID: {session_id}, 기존 세션 종료")
                            try:
                                await manager.sessions[session_id].websocket.close()
                            except:
                                pass
                            manager.disconnect_session(session_id)
                        
                        # 세션 등록
                        session = Session(session_id, websocket)
                        manager.sessions[session_id] = session
                        
                        # 연결 확인 응답
                        await websocket.send_text(json.dumps({
                            "type": "connected",
                            "session_id": session_id,
                            "message": "세션 연결됨"
                        }))
                        
                        logger.info(f"✅ 세션 {session_id} 등록 완료")
                        break
                        
                    else:
                        logger.warning(f"⚠️ 세션 초기화 전 다른 메시지 수신: {message_type}")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "message": "세션을 먼저 시작해주세요"
                        }))
                        
                elif 'bytes' in message:
                    logger.warning(f"⚠️ 세션 초기화 전 바이너리 데이터 수신")
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "세션을 먼저 시작해주세요"
                    }))
                    
            except Exception as e:
                logger.error(f"❌ 메시지 처리 중 오류: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "message": f"메시지 처리 오류: {str(e)}"
                }))
                return
        
        # 메인 메시지 처리 루프
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive(), timeout=30.0)
                
                if 'bytes' in message:
                    # 오디오 데이터 수신
                    audio_data = message['bytes']
                    session.add_audio_data(audio_data)
                    session.status = 'recording'
                    
                    logger.debug(f"🎤 오디오 데이터 수신: {len(audio_data)} bytes (세션: {session_id})")
                    
                elif 'text' in message:
                    # 제어 메시지 처리
                    try:
                        control_msg = json.loads(message['text'])
                        await handle_control_message(session, control_msg)
                    except json.JSONDecodeError as je:
                        logger.error(f"❌ 제어 메시지 JSON 파싱 실패: {je}")
                        await websocket.send_text(json.dumps({
                            "type": "error",
                            "session_id": session_id,
                            "message": f"잘못된 JSON 형식: {je}"
                        }))
                    
            except asyncio.TimeoutError:
                # 타임아웃 시 ping 전송
                if session:
                    try:
                        await websocket.send_text(json.dumps({
                            "type": "ping",
                            "session_id": session_id,
                            "timestamp": asyncio.get_event_loop().time()
                        }))
                        logger.debug(f"📡 Ping 전송 (세션: {session_id})")
                    except Exception as e:
                        logger.error(f"❌ Ping 전송 실패: {e}")
                        break
                    
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 연결 끊어짐 (세션: {session_id})")
    except Exception as e:
        logger.error(f"❌ WebSocket 오류 (세션: {session_id}): {e}")
    finally:
        if session_id:
            manager.disconnect_session(session_id)
        try:
            if hasattr(websocket, 'client_state') and websocket.client_state.value not in [3, 4]:
                await websocket.close()
        except Exception as close_error:
            logger.debug(f"💭 WebSocket 종료 건너뜀: {close_error}")

async def handle_control_message(session: Session, message: dict):
    """제어 메시지 처리 (STT→TTS 파이프라인)"""
    msg_type = message.get('type')
    session_id = session.session_id
    
    logger.info(f"📨 제어 메시지 수신: {msg_type} (세션: {session_id})")
    
    if msg_type == 'recording_resumed':
        session.status = 'recording'
        logger.info(f"🔄 녹음 재개 (세션: {session_id})")
        
    elif msg_type == 'recording_finished':
        # 녹음 완료 - STT → TTS 파이프라인 시작
        session.status = 'processing'
        
        if session.audio_buffer:
            logger.info(f"🔄 STT → TTS 파이프라인 시작 (세션: {session_id})")
            
            # STT 처리 중 상태 전송
            await session.websocket.send_text(json.dumps({
                "type": "processing",
                "session_id": session_id,
                "message": "음성을 텍스트로 변환 중..."
            }))
            
            # 1단계: STT 처리
            combined_audio = session.get_combined_audio()
            stt_result = await process_stt_conversion(session_id, combined_audio)
            
            if stt_result["success"]:
                # STT 성공 - TTS 처리로 진행
                transcription = stt_result["transcription"]
                logger.info(f"🎯 STT 변환 성공 (세션: {session_id}): \"{transcription}\"")
                
                # 2단계: TTS 처리
                session.status = 'converting'
                await session.websocket.send_text(json.dumps({
                    "type": "converting",
                    "session_id": session_id,
                    "message": f"텍스트를 음성으로 변환 중... (인식된 텍스트: {transcription})"
                }))
                
                # TTS 처리 (proto 파일 매칭)
                tts_result = await process_tts_conversion(session_id, transcription)
                
                if tts_result["success"]:
                    # TTS 성공 - 생성된 오디오 전송
                    logger.info(f"✅ TTS 변환 성공 (세션: {session_id})")
                    
                    # 변환된 음성 전송
                    await session.websocket.send_bytes(tts_result["audio_data"])
                    logger.info(f"🔊 음성 변환 완료 및 전송 (세션: {session_id})")
                    
                    # 완료 메시지 전송
                    await session.websocket.send_text(json.dumps({
                        "type": "completed",
                        "session_id": session_id,
                        "message": "음성 변환 완료",
                        "stt_result": {
                            "transcription": transcription,
                            "confidence": stt_result.get("confidence", 0.0),
                            "processing_time_ms": stt_result.get("processing_time_ms", 0)
                        },
                        "tts_result": {
                            "processing_time_ms": tts_result.get("processing_time_ms", 0),
                            "audio_duration_ms": tts_result.get("stats", {}).get("audio_duration_ms", 0) if tts_result.get("stats") else 0
                        }
                    }))
                    
                else:
                    # TTS 실패
                    logger.error(f"❌ TTS 처리 실패 (세션: {session_id}): {tts_result.get('error', '알 수 없는 오류')}")
                    await session.websocket.send_text(json.dumps({
                        "type": "error",
                        "session_id": session_id,
                        "message": f"음성 합성 실패: {tts_result.get('error', '알 수 없는 오류')}"
                    }))
                
            else:
                # STT 실패
                logger.error(f"❌ STT 처리 실패 (세션: {session_id}): {stt_result.get('error', '알 수 없는 오류')}")
                await session.websocket.send_text(json.dumps({
                    "type": "error",
                    "session_id": session_id,
                    "message": f"음성 인식 실패: {stt_result.get('error', '알 수 없는 오류')}"
                }))
            
            # 버퍼 정리
            session.clear_audio_buffer()
            session.status = 'completed'
            
        else:
            logger.warning(f"⚠️ 오디오 데이터가 없음 (세션: {session_id})")
            await session.websocket.send_text(json.dumps({
                "type": "error",
                "session_id": session_id,
                "message": "오디오 데이터가 없습니다"
            }))

async def process_stt_conversion(session_id: int, audio_data: bytes) -> dict:
    """STT gRPC 서버를 통한 음성-텍스트 변환"""
    try:
        logger.info(f"🎤 gRPC STT 변환 시작 (세션: {session_id}, {len(audio_data)} bytes)")
        
        stt_client = await get_stt_client()
        
        if hasattr(stt_client, 'is_connected') and not stt_client.is_connected():
            logger.warning(f"⚠️ STT 서버에 연결되지 않음 (세션: {session_id})")
            return {
                "success": False,
                "error": "STT 서버에 연결할 수 없습니다",
                "transcription": "",
                "confidence": 0.0
            }
        
        result = await stt_client.process_stt(
            audio_data=audio_data,
            session_id=session_id,
            language="korean"
        )
        
        if result.get("success"):
            logger.info(f"✅ gRPC STT 변환 성공 (세션: {session_id})")
            logger.info(f"📝 변환된 텍스트: \"{result.get('transcription', '')}\" (신뢰도: {result.get('confidence', 0.0):.2f})")
        else:
            logger.error(f"❌ gRPC STT 변환 실패 (세션: {session_id}): {result.get('error', '알 수 없는 오류')}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ STT 변환 중 예외 발생 (세션: {session_id}): {e}")
        return {
            "success": False,
            "error": f"STT 변환 중 오류: {str(e)}",
            "transcription": "",
            "confidence": 0.0
        }

async def process_tts_conversion(session_id: int, text: str) -> dict:
    """TTS gRPC 서버를 통한 텍스트-음성 변환 (proto 파일 매칭)"""
    try:
        logger.info(f"🔊 gRPC TTS 변환 시작 (세션: {session_id}, 텍스트: '{text[:50]}{'...' if len(text) > 50 else ''}')")
        
        tts_client = await get_tts_client()
        
        if hasattr(tts_client, 'is_connected') and not tts_client.is_connected():
            logger.warning(f"⚠️ TTS 서버에 연결되지 않음 (세션: {session_id})")
            return {
                "success": False,
                "error": "TTS 서버에 연결할 수 없습니다",
                "audio_data": None
            }
        
        # proto 파일 매칭된 TTS 호출
        result = await tts_client.process_tts(
            text=text,
            session_id=session_id,
            voice="female",      # proto의 voice 필드
            language="korean",   # proto의 language 필드
            speed=1.0,          # proto의 speed 필드
            pitch=1.0           # proto의 pitch 필드
        )
        
        if result.get("success"):
            logger.info(f"✅ gRPC TTS 변환 성공 (세션: {session_id})")
            logger.info(f"🔊 생성된 오디오: {len(result.get('audio_data', b''))}바이트")
        else:
            logger.error(f"❌ gRPC TTS 변환 실패 (세션: {session_id}): {result.get('error', '알 수 없는 오류')}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ TTS 변환 중 예외 발생 (세션: {session_id}): {e}")
        return {
            "success": False,
            "error": f"TTS 변환 중 오류: {str(e)}",
            "audio_data": None
        }

def create_wav_from_pcm(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """PCM 데이터를 WAV 포맷으로 변환 (백업용, TTS는 이미 WAV 형식 반환)"""
    try:
        buffer = io.BytesIO()
        
        with wave.open(buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16bit = 2 bytes
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_data)
        
        return buffer.getvalue()
    except Exception as e:
        logger.error(f"❌ WAV 변환 실패: {e}")
        return pcm_data  # 실패 시 원본 반환

@router.websocket("/status")
async def websocket_status(websocket: WebSocket):
    """서버 상태 모니터링"""
    connection_id = await manager.connect_status(websocket)
    
    try:
        while True:
            # 현재 세션들의 상태 수집
            session_statuses = {}
            for sid, session in manager.sessions.items():
                session_statuses[sid] = {
                    "status": session.status,
                    "audio_buffer_size": len(session.audio_buffer),
                    "created_at": session.created_at,
                    "last_audio_time": session.last_audio_time
                }
            
            # STT, TTS 클라이언트 상태 확인
            try:
                stt_client = await get_stt_client()
                stt_connected = hasattr(stt_client, 'is_connected') and stt_client.is_connected()
            except:
                stt_connected = False
                
            try:
                tts_client = await get_tts_client()
                tts_connected = hasattr(tts_client, 'is_connected') and tts_client.is_connected()
            except:
                tts_connected = False
            
            status = {
                "type": "status",
                "timestamp": asyncio.get_event_loop().time(),
                "total_sessions": manager.get_session_count(),
                "sessions": session_statuses,
                "server_info": {
                    "active_connections": len(manager.status_connections),
                    "uptime": asyncio.get_event_loop().time(),
                    "stt_connected": stt_connected,
                    "tts_connected": tts_connected
                }
            }
            
            await websocket.send_text(json.dumps(status))
            await asyncio.sleep(1)  # 1초마다 상태 전송
            
    except WebSocketDisconnect:
        logger.info(f"🔌 상태 WebSocket 연결 끊어짐 (연결: {connection_id})")
    except Exception as e:
        logger.error(f"❌ 상태 WebSocket 오류 (연결: {connection_id}): {e}")
    finally:
        manager.disconnect_status(connection_id)

# 추가 API 엔드포인트들
@router.get("/sessions")
async def get_active_sessions():
    """활성 세션 목록 조회"""
    sessions = []
    for session_id, session in manager.sessions.items():
        sessions.append({
            "session_id": session_id,
            "status": session.status,
            "audio_buffer_size": len(session.audio_buffer),
            "created_at": session.created_at,
            "last_audio_time": session.last_audio_time
        })
    
    # STT, TTS 연결 상태 추가
    try:
        stt_client = await get_stt_client()
        stt_connected = hasattr(stt_client, 'is_connected') and stt_client.is_connected()
    except:
        stt_connected = False
        
    try:
        tts_client = await get_tts_client()
        tts_connected = hasattr(tts_client, 'is_connected') and tts_client.is_connected()
    except:
        tts_connected = False
    
    return {
        "total_sessions": len(sessions),
        "sessions": sessions,
        "stt_connected": stt_connected,
        "tts_connected": tts_connected
    }

@router.delete("/sessions/{session_id}")
async def terminate_session(session_id: int):
    """특정 세션 강제 종료"""
    session = manager.get_session(session_id)
    if session:
        try:
            await session.websocket.close()
            manager.disconnect_session(session_id)
            return {"message": f"세션 {session_id} 종료됨"}
        except Exception as e:
            return {"error": f"세션 종료 실패: {str(e)}"}
    else:
        return {"error": "세션을 찾을 수 없음"}

# 참고: 이벤트 핸들러는 main.py나 app 레벨에서 처리해야 함
# @app.on_event("shutdown")
# async def shutdown_event():
#     """애플리케이션 종료 시 gRPC 클라이언트 정리"""
#     logger.info("🧹 애플리케이션 종료, gRPC 클라이언트 정리 중...")
#     await cleanup_grpc_clients()
#     logger.info("✅ 정리 완료")