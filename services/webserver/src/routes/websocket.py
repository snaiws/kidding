from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import asyncio
import json
from typing import Dict, Optional
import io
import wave
import logging

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
    """실시간 음성 데이터 처리"""
    session: Optional[Session] = None
    session_id = None
    
    try:
        # 초기 연결 수락
        await websocket.accept()
        logger.info("🔗 WebSocket 연결 수락됨")
        
        # 첫 번째 메시지에서 세션 ID 대기
        try:
            first_message = await asyncio.wait_for(websocket.receive(), timeout=10.0)
            
            if 'text' in first_message:
                init_data = json.loads(first_message['text'])
                if init_data.get('type') == 'session_start':
                    session_id = init_data.get('session_id')
                    logger.info(f"📋 세션 시작 요청: {session_id}")
                    
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
                else:
                    raise ValueError("유효하지 않은 초기화 메시지")
            else:
                raise ValueError("텍스트 메시지가 필요함")
                
        except (asyncio.TimeoutError, ValueError) as e:
            logger.error(f"❌ 세션 초기화 실패: {e}")
            await websocket.close(code=1003, reason="세션 초기화 실패")
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
                    control_msg = json.loads(message['text'])
                    await handle_control_message(session, control_msg)
                    
            except asyncio.TimeoutError:
                # 타임아웃 시 ping 전송
                if session:
                    await websocket.send_text(json.dumps({
                        "type": "ping",
                        "session_id": session_id,
                        "timestamp": asyncio.get_event_loop().time()
                    }))
                    
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket 연결 끊어짐 (세션: {session_id})")
    except Exception as e:
        logger.error(f"❌ WebSocket 오류 (세션: {session_id}): {e}")
        try:
            if session:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "session_id": session_id,
                    "message": f"서버 오류: {str(e)}"
                }))
        except:
            pass
    finally:
        if session_id:
            manager.disconnect_session(session_id)
        try:
            await websocket.close()
        except:
            pass

async def handle_control_message(session: Session, message: dict):
    """제어 메시지 처리"""
    msg_type = message.get('type')
    session_id = session.session_id
    
    logger.info(f"📨 제어 메시지 수신: {msg_type} (세션: {session_id})")
    
    if msg_type == 'recording_resumed':
        # 녹음 재개
        session.status = 'recording'
        logger.info(f"🔄 녹음 재개 (세션: {session_id})")
        
    elif msg_type == 'recording_finished':
        # 녹음 완료 - 변환 처리 시작
        session.status = 'processing'
        
        if session.audio_buffer:
            logger.info(f"🔄 음성 변환 시작 (세션: {session_id})")
            
            # 처리 중 상태 전송
            await session.websocket.send_text(json.dumps({
                "type": "processing",
                "session_id": session_id,
                "message": "음성 변환 중..."
            }))
            
            # 음성 변환 처리
            combined_audio = session.get_combined_audio()
            converted_audio = await process_voice_conversion(session_id, combined_audio)
            
            # 변환 완료 상태로 변경
            session.status = 'converting'
            
            # 변환된 음성 전송
            await session.websocket.send_bytes(converted_audio)
            logger.info(f"✅ 변환된 음성 전송 완료 (세션: {session_id})")
            
            # 완료 메시지 전송
            await session.websocket.send_text(json.dumps({
                "type": "completed",
                "session_id": session_id,
                "message": "음성 변환 완료"
            }))
            
            # 버퍼 정리
            session.clear_audio_buffer()
            session.status = 'completed'
            
            # 연결 종료는 클라이언트에서 처리
            
        else:
            logger.warning(f"⚠️ 오디오 데이터가 없음 (세션: {session_id})")

async def process_voice_conversion(session_id: int, audio_data: bytes) -> bytes:
    """음성 변환 로직"""
    logger.info(f"🔄 음성 변환 처리 중... (세션: {session_id}, {len(audio_data)} bytes)")
    
    # 실제 처리 시간 시뮬레이션 (1-3초)
    processing_time = 1.5
    await asyncio.sleep(processing_time)
    
    # 실제 AI 음성 변환 로직이 여기에 들어감
    # 현재는 임시로 WAV 형태로 변환만 수행
    
    wav_audio = create_wav_from_pcm(audio_data, sample_rate=16000)
    
    logger.info(f"✅ 음성 변환 완료 (세션: {session_id}, {len(wav_audio)} bytes)")
    return wav_audio

def create_wav_from_pcm(pcm_data: bytes, sample_rate: int = 16000) -> bytes:
    """PCM 데이터를 WAV 포맷으로 변환"""
    buffer = io.BytesIO()
    
    with wave.open(buffer, 'wb') as wav_file:
        wav_file.setnchannels(1)  # mono
        wav_file.setsampwidth(2)  # 16bit = 2 bytes
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)
    
    return buffer.getvalue()

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
            
            status = {
                "type": "status",
                "timestamp": asyncio.get_event_loop().time(),
                "total_sessions": manager.get_session_count(),
                "sessions": session_statuses,
                "server_info": {
                    "active_connections": len(manager.status_connections),
                    "uptime": asyncio.get_event_loop().time()
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
    
    return {
        "total_sessions": len(sessions),
        "sessions": sessions
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