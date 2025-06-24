import { AudioProcessor } from './audio_processor.js';

/**
 * 세션 클래스 - 개별 녹음 세션을 관리
 */
class Session {
    constructor(id, websocket) {
        this.id = id;
        this.websocket = websocket;
        this.audioProcessor = null;
        this.status = 'connecting'; // connecting, connected, recording, waiting_reconnect, processing, playing, completed, error
        this.createdAt = Date.now();
    }
    
    /**
     * 녹음 시작
     * @param {Function} onDataCallback - 오디오 데이터 콜백
     */
    async startRecording(onDataCallback) {
        this.audioProcessor = new AudioProcessor();
        await this.audioProcessor.start(onDataCallback);
        this.status = 'recording';
    }
    
    /**
     * 녹음 재개
     */
    resumeRecording() {
        if (this.audioProcessor) {
            this.status = 'recording';
        }
    }
    
    /**
     * 녹음 일시정지
     */
    pauseRecording() {
        this.status = 'waiting_reconnect';
    }
    
    /**
     * 녹음 완료 및 정리
     */
    stopRecording() {
        if (this.audioProcessor) {
            this.audioProcessor.stop();
            this.audioProcessor = null;
        }
        this.status = 'processing';
    }
    
    /**
     * 세션 정리
     */
    cleanup() {
        if (this.audioProcessor) {
            this.audioProcessor.stop();
            this.audioProcessor = null;
        }
        
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.close();
        }
        
        this.status = 'completed';
    }
    
    /**
     * 메시지 전송
     * @param {Object} message - 전송할 메시지 객체
     */
    sendMessage(message) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify(message));
        }
    }
    
    /**
     * 오디오 데이터 전송
     * @param {ArrayBuffer} audioData - 전송할 오디오 데이터
     */
    sendAudioData(audioData) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(audioData);
        }
    }
}

/**
 * 세션 매니저 - 여러 세션을 관리하는 클래스
 */
class SessionManager {
    constructor() {
        this.sessions = new Map();
        this.sessionCounter = 0;
        this.currentSession = null;
        this.reconnectTimer = null;
        this.lastReleaseTime = 0;
        this.RECONNECT_THRESHOLD = 1000; // 1초
        
        // 이벤트 핸들러들
        this.onSessionUpdate = null;
        this.onAudioReceived = null;
        this.onSessionError = null;
    }
    
    /**
     * 새 세션 생성
     * @returns {Promise<number>} 세션 ID
     */
    async createSession() {
        const sessionId = ++this.sessionCounter;
        
        try {
            const ws = new WebSocket('ws://localhost:8000/ws/audio');
            ws.binaryType = 'arraybuffer';
            
            const session = new Session(sessionId, ws);
            this.sessions.set(sessionId, session);
            this.currentSession = sessionId;
            
            this.setupWebSocketHandlers(session);
            
            return sessionId;
            
        } catch (error) {
            console.error(`❌ 세션 생성 실패 (${sessionId}):`, error);
            throw error;
        }
    }
    
    /**
     * WebSocket 이벤트 핸들러 설정
     * @param {Session} session 
     */
    setupWebSocketHandlers(session) {
        const ws = session.websocket;
        
        ws.onopen = async () => {
            console.log(`✅ WebSocket 연결됨 (세션: ${session.id})`);
            session.status = 'connected';
            
            // 세션 시작 메시지 전송
            session.sendMessage({
                type: 'session_start',
                session_id: session.id,
                timestamp: Date.now()
            });
            
            await this.startRecording(session);
            this.notifySessionUpdate(session);
        };
        
        ws.onmessage = (event) => {
            this.handleWebSocketMessage(session, event);
        };
        
        ws.onerror = (error) => {
            console.error(`❌ WebSocket 오류 (세션: ${session.id}):`, error);
            this.handleSessionError(session.id);
        };
        
        ws.onclose = () => {
            console.log(`🔌 WebSocket 종료 (세션: ${session.id})`);
            this.cleanupSession(session.id);
        };
    }
    
    /**
     * 녹음 시작
     * @param {Session} session 
     */
    async startRecording(session) {
        try {
            await session.startRecording((pcmData) => {
                if (session.status === 'recording') {
                    // PCM을 Int16으로 변환하여 전송
                    const int16Data = new Int16Array(pcmData.length);
                    for (let i = 0; i < pcmData.length; i++) {
                        int16Data[i] = Math.max(-32768, Math.min(32767, pcmData[i] * 32768));
                    }
                    session.sendAudioData(int16Data.buffer);
                }
            });
            
            this.notifySessionUpdate(session);
            console.log(`✅ 녹음 시작됨 (세션: ${session.id})`);
            
        } catch (error) {
            console.error(`❌ 녹음 시작 오류 (세션: ${session.id}):`, error);
            this.handleSessionError(session.id);
        }
    }
    
    /**
     * 현재 세션 일시정지
     */
    pauseCurrentSession() {
        if (this.currentSession) {
            const session = this.sessions.get(this.currentSession);
            if (session && session.status === 'recording') {
                session.pauseRecording();
                this.notifySessionUpdate(session);
                
                // 재연결 타이머 설정
                this.reconnectTimer = setTimeout(() => {
                    this.finalizeCurrentSession();
                }, this.RECONNECT_THRESHOLD);
                
                console.log(`⏸️ 세션 일시정지 (세션: ${session.id})`);
            }
        }
    }
    
    /**
     * 현재 세션 재개 또는 새 세션 시작
     */
    async resumeOrStartSession() {
        const now = Date.now();
        const timeSinceLastRelease = now - this.lastReleaseTime;
        
        // 1초 이내에 다시 눌렀고 현재 세션이 대기 중이면 재개
        if (timeSinceLastRelease < this.RECONNECT_THRESHOLD && this.currentSession) {
            const session = this.sessions.get(this.currentSession);
            if (session && session.status === 'waiting_reconnect') {
                this.clearReconnectTimer();
                session.resumeRecording();
                
                // 재개 신호 전송
                session.sendMessage({
                    type: 'recording_resumed',
                    session_id: session.id,
                    timestamp: Date.now()
                });
                
                this.notifySessionUpdate(session);
                console.log(`🔄 세션 재개 (세션: ${session.id})`);
                return session.id;
            }
        }
        
        // 새 세션 시작
        return await this.createSession();
    }
    
    /**
     * 현재 세션 완료 처리
     */
    finalizeCurrentSession() {
        if (this.currentSession) {
            const session = this.sessions.get(this.currentSession);
            if (session) {
                this.clearReconnectTimer();
                session.stopRecording();
                
                // 완료 신호 전송
                session.sendMessage({
                    type: 'recording_finished',
                    session_id: session.id,
                    timestamp: Date.now()
                });
                
                this.currentSession = null;
                this.notifySessionUpdate(session);
                console.log(`⏹️ 세션 완료 (세션: ${session.id})`);
            }
        }
    }
    
    /**
     * WebSocket 메시지 처리
     * @param {Session} session 
     * @param {MessageEvent} event 
     */
    handleWebSocketMessage(session, event) {
        if (typeof event.data === 'string') {
            const message = JSON.parse(event.data);
            console.log(`📨 메시지 수신 (세션: ${session.id}):`, message.type);
            
            switch (message.type) {
                case 'connected':
                    break;
                case 'processing':
                    session.status = 'processing';
                    this.notifySessionUpdate(session);
                    break;
                case 'completed':
                    break;
            }
        } else {
            // 변환된 오디오 데이터
            console.log(`🔊 오디오 수신 (세션: ${session.id}):`, event.data.byteLength, 'bytes');
            session.status = 'playing';
            this.notifySessionUpdate(session);
            
            if (this.onAudioReceived) {
                this.onAudioReceived(session.id, event.data);
            }
        }
    }
    
    /**
     * 세션 에러 처리
     * @param {number} sessionId 
     */
    handleSessionError(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.status = 'error';
            
            if (this.currentSession === sessionId) {
                this.currentSession = null;
            }
            
            this.clearReconnectTimer();
            this.notifySessionUpdate(session);
            
            if (this.onSessionError) {
                this.onSessionError(sessionId);
            }
        }
    }
    
    /**
     * 세션 정리
     * @param {number} sessionId 
     */
    cleanupSession(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.cleanup();
            this.sessions.delete(sessionId);
            
            if (this.currentSession === sessionId) {
                this.currentSession = null;
            }
            
            console.log(`🧹 세션 정리 완료 (세션: ${sessionId})`);
            this.notifySessionUpdate(null);
        }
    }
    
    /**
     * 세션 완료 처리
     * @param {number} sessionId 
     */
    completeSession(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            session.status = 'completed';
            this.notifySessionUpdate(session);
            
            // 잠시 후 정리
            setTimeout(() => {
                this.cleanupSession(sessionId);
            }, 1000);
        }
    }
    
    /**
     * 재연결 타이머 정리
     */
    clearReconnectTimer() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }
    
    /**
     * 세션 업데이트 알림
     * @param {Session} session 
     */
    notifySessionUpdate(session) {
        if (this.onSessionUpdate) {
            this.onSessionUpdate(session, this.sessions.size);
        }
    }
    
    /**
     * 마지막 릴리즈 시간 설정
     */
    setLastReleaseTime() {
        this.lastReleaseTime = Date.now();
    }
    
    /**
     * 활성 세션 수 반환
     * @returns {number}
     */
    getActiveSessionCount() {
        return this.sessions.size;
    }
    
    /**
     * 특정 상태의 세션 수 반환
     * @param {string} status 
     * @returns {number}
     */
    getSessionCountByStatus(status) {
        return Array.from(this.sessions.values())
            .filter(session => session.status === status).length;
    }
}

export { SessionManager, Session };