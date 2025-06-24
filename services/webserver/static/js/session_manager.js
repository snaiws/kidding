/**
 * 파일: frontend/js/session_manager.js
 * 설명: 커넥션 풀을 사용한 세션 관리 클래스 (업데이트됨)
 * 변경사항: 
 * - 커넥션 풀 통합으로 즉시 녹음 시작
 * - connecting 단계 제거
 * - 1초 재연결 로직 제거, 각 녹음은 독립적 세션
 */
import { AudioProcessor } from './audio_processor.js';
import { ConnectionPoolManager } from './connection_pool_manager.js';

/**
 * 세션 클래스 - 개별 녹음 세션을 관리
 */
class Session {
    constructor(id, connection) {
        this.id = id;
        this.connection = connection;
        this.websocket = connection.websocket;
        this.audioProcessor = null;
        this.status = 'ready'; // ready, recording, processing, playing, completed, error
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
 * 세션 매니저 - 커넥션 풀을 사용한 세션 관리
 */
class SessionManager {
    constructor() {
        this.sessions = new Map();
        this.sessionCounter = 0;
        this.currentSession = null;
        this.connectionPool = new ConnectionPoolManager(3); // 3개 커넥션 풀
        this.finalizationTimer = null;
        this.FINALIZATION_DELAY = 1000; // 1초
        
        // 이벤트 핸들러들
        this.onSessionUpdate = null;
        this.onAudioReceived = null;
        this.onSessionError = null;
        this.onPoolStatusChange = null;
        
        // 커넥션 풀 이벤트 설정
        this.setupConnectionPoolEvents();
    }
    
    /**
     * 세션 매니저 초기화
     */
    async initialize() {
        console.log('🚀 SessionManager 초기화 시작...');
        await this.connectionPool.initialize();
        console.log('✅ SessionManager 초기화 완료');
    }
    
    /**
     * 커넥션 풀 이벤트 설정
     */
    setupConnectionPoolEvents() {
        this.connectionPool.onPoolStatusChange = (status) => {
            if (this.onPoolStatusChange) {
                this.onPoolStatusChange(status);
            }
        };
    }
    
    /**
     * 새 세션 생성 및 즉시 녹음 시작
     * @returns {Promise<number>} 세션 ID
     */
    async createSessionAndStartRecording() {
        // 커넥션 풀에서 사용 가능한 커넥션 가져오기
        const connection = this.connectionPool.assignConnectionToSession(`temp_${Date.now()}`);
        if (!connection) {
            throw new Error('사용 가능한 커넥션이 없습니다. 잠시 후 다시 시도해주세요.');
        }
        
        const sessionId = ++this.sessionCounter;
        
        // 임시 세션 ID를 실제 세션 ID로 업데이트
        this.connectionPool.busyConnections.delete(`temp_${Date.now()}`);
        connection.sessionId = sessionId;
        this.connectionPool.busyConnections.set(sessionId, connection);
        
        const session = new Session(sessionId, connection);
        this.sessions.set(sessionId, session);
        this.currentSession = sessionId;
        
        this.setupWebSocketHandlers(session);
        
        try {
            // 세션 시작 메시지 전송
            session.sendMessage({
                type: 'session_start',
                session_id: sessionId,
                timestamp: Date.now()
            });
            
            // 즉시 녹음 시작
            await this.startRecording(session);
            
            console.log(`✅ 세션 생성 및 녹음 시작: ${sessionId}`);
            return sessionId;
            
        } catch (error) {
            console.error(`❌ 세션 생성 실패 (${sessionId}):`, error);
            this.cleanupSession(sessionId);
            throw error;
        }
    }
    
    /**
     * WebSocket 이벤트 핸들러 설정
     * @param {Session} session 
     */
    setupWebSocketHandlers(session) {
        const ws = session.websocket;
        
        // 이미 연결된 상태이므로 onopen은 호출되지 않음
        
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
     * 현재 세션 녹음 중지
     */
    stopCurrentSessionRecording() {
        if (this.currentSession) {
            const session = this.sessions.get(this.currentSession);
            if (session && session.status === 'recording') {
                session.stopRecording();
                
                // 완료 신호 전송
                session.sendMessage({
                    type: 'recording_finished',
                    session_id: session.id,
                    timestamp: Date.now()
                });
                
                this.notifySessionUpdate(session);
                console.log(`⏹️ 세션 녹음 중지 (세션: ${session.id})`);
                
                // 1초 후 세션 완료 처리 타이머 설정
                this.finalizationTimer = setTimeout(() => {
                    this.finalizeSession(session.id);
                }, this.FINALIZATION_DELAY);
            }
        }
    }
    
    /**
     * 세션 완료 처리
     * @param {number} sessionId 
     */
    finalizeSession(sessionId) {
        const session = this.sessions.get(sessionId);
        if (session) {
            this.currentSession = null;
            this.clearFinalizationTimer();
            
            // 커넥션은 서버에서 오디오 응답을 받은 후 자동으로 종료됨
            console.log(`⏹️ 세션 완료 처리 (세션: ${sessionId})`);
        }
    }
    
    /**
     * 새 녹음 시작 (기존 세션이 있으면 즉시 완료 처리)
     */
    async startNewRecording() {
        // 기존 세션이 있으면 즉시 완료 처리
        if (this.currentSession) {
            this.clearFinalizationTimer();
            this.finalizeSession(this.currentSession);
        }
        
        // 새 세션 시작
        return await this.createSessionAndStartRecording();
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
            
            this.clearFinalizationTimer();
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
            
            // 커넥션 풀로 커넥션 반환
            this.connectionPool.releaseConnection(sessionId);
            
            console.log(`🧹 세션 정리 완료 (세션: ${sessionId})`);
            this.notifySessionUpdate(null);
        }
    }
    
    /**
     * 세션 완료 처리 (오디오 재생 후)
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
     * 완료 타이머 정리
     */
    clearFinalizationTimer() {
        if (this.finalizationTimer) {
            clearTimeout(this.finalizationTimer);
            this.finalizationTimer = null;
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
     * 새 녹음 가능 여부 확인
     * @returns {boolean}
     */
    canStartNewRecording() {
        const poolStatus = this.connectionPool.getPoolStatus();
        return poolStatus.canAcceptNewSession;
    }
    
    /**
     * 커넥션 풀 상태 반환
     * @returns {Object}
     */
    getPoolStatus() {
        return this.connectionPool.getPoolStatus();
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
    
    /**
     * 전체 정리
     */
    destroy() {
        console.log('🧹 SessionManager 정리 중...');
        
        this.clearFinalizationTimer();
        
        // 모든 세션 정리
        this.sessions.forEach((session, sessionId) => {
            this.cleanupSession(sessionId);
        });
        
        // 커넥션 풀 정리
        this.connectionPool.destroy();
        
        console.log('✅ SessionManager 정리 완료');
    }
}

export { SessionManager, Session };