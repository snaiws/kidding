import { SessionManager } from './session_manager.js';
import { UIManager } from './ui_manager.js';

/**
 * 메인 VoiceConverter 클래스
 * 세션 관리와 UI 관리를 통합하여 전체 애플리케이션을 제어
 */
class VoiceConverter {
    constructor() {
        console.log('🚀 VoiceConverter 초기화 시작...');
        
        // 모듈 초기화
        this.sessionManager = new SessionManager();
        this.uiManager = new UIManager();
        
        // 이벤트 핸들러 바인딩
        this.bindEvents();
        this.setupEventHandlers();
        
        console.log('✅ VoiceConverter 초기화 완료');
    }
    
    /**
     * UI 이벤트 핸들러 바인딩
     */
    bindEvents() {
        const voiceBtn = document.getElementById('voiceBtn');
        let isPressed = false;
        
        // 기본 이벤트 방지
        voiceBtn.addEventListener('click', (e) => e.preventDefault());
        voiceBtn.addEventListener('contextmenu', (e) => e.preventDefault());
        voiceBtn.addEventListener('dragstart', (e) => e.preventDefault());
        
        // 마우스 이벤트
        voiceBtn.addEventListener('mousedown', (e) => {
            e.preventDefault();
            if (!isPressed) {
                isPressed = true;
                this.handlePressStart();
            }
        });
        
        voiceBtn.addEventListener('mouseup', (e) => {
            e.preventDefault();
            if (isPressed) {
                isPressed = false;
                this.handlePressEnd();
            }
        });
        
        voiceBtn.addEventListener('mouseleave', (e) => {
            if (isPressed) {
                isPressed = false;
                this.handlePressEnd();
            }
        });
        
        // 터치 이벤트
        voiceBtn.addEventListener('touchstart', (e) => {
            e.preventDefault();
            if (!isPressed) {
                isPressed = true;
                this.handlePressStart();
            }
        });
        
        voiceBtn.addEventListener('touchend', (e) => {
            e.preventDefault();
            if (isPressed) {
                isPressed = false;
                this.handlePressEnd();
            }
        });
        
        voiceBtn.addEventListener('touchcancel', (e) => {
            e.preventDefault();
            if (isPressed) {
                isPressed = false;
                this.handlePressEnd();
            }
        });
        
        // 전역 이벤트
        document.addEventListener('mouseup', (e) => {
            if (isPressed && !voiceBtn.contains(e.target)) {
                isPressed = false;
                this.handlePressEnd();
            }
        });
        
        document.addEventListener('touchend', (e) => {
            if (isPressed && !voiceBtn.contains(e.target)) {
                isPressed = false;
                this.handlePressEnd();
            }
        });
        
        console.log('🎛️ UI 이벤트 핸들러 바인딩 완료');
    }
    
    /**
     * 세션 매니저와 UI 매니저 간 이벤트 핸들러 설정
     */
    setupEventHandlers() {
        // 세션 업데이트 시 UI 업데이트
        this.sessionManager.onSessionUpdate = (session, totalSessions) => {
            this.handleSessionUpdate(session, totalSessions);
        };
        
        // 오디오 수신 시 재생 처리
        this.sessionManager.onAudioReceived = async (sessionId, audioData) => {
            await this.handleAudioReceived(sessionId, audioData);
        };
        
        // 세션 에러 시 UI 처리
        this.sessionManager.onSessionError = (sessionId) => {
            this.handleSessionError(sessionId);
        };
    }
    
    /**
     * 버튼 눌림 처리
     */
    async handlePressStart() {
        console.log('🎤 버튼 눌림 감지');
        
        try {
            this.uiManager.updateButtonState('connecting');
            this.uiManager.updateSystemStatus('stt', 'CONNECTING');
            
            const sessionId = await this.sessionManager.resumeOrStartSession();
            console.log(`✅ 세션 시작/재개: ${sessionId}`);
            
        } catch (error) {
            console.error('❌ 세션 시작 오류:', error);
            this.uiManager.updateButtonState('ready');
            this.uiManager.updateSystemStatus('stt', 'ERROR');
            this.uiManager.showToast('연결 오류가 발생했습니다.', 'error');
        }
    }
    
    /**
     * 버튼 릴리즈 처리
     */
    handlePressEnd() {
        console.log('🔽 버튼 릴리즈 감지');
        
        this.sessionManager.setLastReleaseTime();
        this.sessionManager.pauseCurrentSession();
        
        this.uiManager.updateButtonState('waiting');
        this.uiManager.updateSystemStatus('stt', 'PAUSED');
    }
    
    /**
     * 세션 업데이트 처리
     * @param {Session} session 
     * @param {number} totalSessions 
     */
    handleSessionUpdate(session, totalSessions) {
        // 연결 수 업데이트
        this.uiManager.updateConnectionCount(totalSessions);
        
        if (!session) return;
        
        // 세션 상태에 따른 UI 업데이트
        switch (session.status) {
            case 'connecting':
                this.uiManager.updateButtonState('connecting');
                this.uiManager.updateSystemStatus('stt', 'CONNECTING');
                break;
                
            case 'connected':
                this.uiManager.updateSystemStatus('stt', 'CONNECTED');
                break;
                
            case 'recording':
                this.uiManager.updateButtonState('recording');
                this.uiManager.updateSystemStatus('stt', 'RECORDING');
                this.uiManager.updateSystemStatus('voice', 'IDLE');
                break;
                
            case 'waiting_reconnect':
                this.uiManager.updateButtonState('waiting');
                this.uiManager.updateSystemStatus('stt', 'PAUSED');
                break;
                
            case 'processing':
                this.uiManager.updateButtonState('ready');
                this.uiManager.updateSystemStatus('stt', 'IDLE');
                this.uiManager.updateSystemStatus('voice', 'PROCESSING');
                break;
                
            case 'playing':
                this.uiManager.updateSystemStatus('voice', 'IDLE');
                this.uiManager.updateSystemStatus('tts', 'PLAYING');
                this.uiManager.showPlaybackIndicator(true);
                break;
                
            case 'completed':
                this.uiManager.updateSystemStatus('tts', 'IDLE');
                this.uiManager.showPlaybackIndicator(false);
                break;
                
            case 'error':
                this.uiManager.updateButtonState('ready');
                this.uiManager.updateSystemStatus('stt', 'ERROR');
                this.uiManager.updateSystemStatus('voice', 'ERROR');
                break;
        }
        
        // 전체 상태 업데이트
        this.updateOverallStatus();
    }
    
    /**
     * 오디오 수신 및 재생 처리
     * @param {number} sessionId 
     * @param {ArrayBuffer} audioData 
     */
    async handleAudioReceived(sessionId, audioData) {
        console.log(`🔊 오디오 재생 시작 (세션: ${sessionId})`);
        
        try {
            await this.uiManager.playAudio(audioData);
            console.log(`✅ 오디오 재생 완료 (세션: ${sessionId})`);
            
            // 세션 완료 처리
            this.sessionManager.completeSession(sessionId);
            this.uiManager.showToast(`음성 변환 완료! (세션: ${sessionId})`, 'success');
            
        } catch (error) {
            console.error(`❌ 오디오 재생 오류 (세션: ${sessionId}):`, error);
            this.sessionManager.handleSessionError(sessionId);
            this.uiManager.showToast('오디오 재생 중 오류가 발생했습니다.', 'error');
        }
    }
    
    /**
     * 세션 에러 처리
     * @param {number} sessionId 
     */
    handleSessionError(sessionId) {
        console.error(`❌ 세션 에러 (세션: ${sessionId})`);
        this.uiManager.showToast(`세션 ${sessionId}에서 오류가 발생했습니다.`, 'error');
    }
    
    /**
     * 전체 상태 업데이트
     */
    updateOverallStatus() {
        const playingCount = this.sessionManager.getSessionCountByStatus('playing');
        const processingCount = this.sessionManager.getSessionCountByStatus('processing');
        
        // 재생 인디케이터 업데이트
        this.uiManager.showPlaybackIndicator(playingCount > 0);
        
        // 로그 출력
        const totalSessions = this.sessionManager.getActiveSessionCount();
        console.log(`📊 상태 업데이트 - 총 세션: ${totalSessions}, 재생중: ${playingCount}, 처리중: ${processingCount}`);
    }
    
    /**
     * 애플리케이션 종료 시 정리
     */
    destroy() {
        console.log('🧹 VoiceConverter 정리 중...');
        
        // 모든 세션 정리
        this.sessionManager.sessions.forEach((session, sessionId) => {
            this.sessionManager.cleanupSession(sessionId);
        });
        
        // UI 정리
        this.uiManager.destroy();
        
        console.log('✅ VoiceConverter 정리 완료');
    }
    
    /**
     * 디버그 정보 출력
     */
    getDebugInfo() {
        return {
            activeSessions: this.sessionManager.getActiveSessionCount(),
            currentSession: this.sessionManager.currentSession,
            sessionStatuses: Array.from(this.sessionManager.sessions.values()).map(s => ({
                id: s.id,
                status: s.status,
                createdAt: s.createdAt
            })),
            uiConnected: this.uiManager.isConnected
        };
    }
}

// 전역 변수로 인스턴스 저장 (디버깅용)
let voiceConverter;

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', () => {
    console.log('📄 DOM 로드 완료, VoiceConverter 초기화...');
    voiceConverter = new VoiceConverter();
    
    // 전역 디버그 함수 등록
    window.getVoiceConverterDebugInfo = () => voiceConverter.getDebugInfo();
});

// 페이지 언로드 시 정리
window.addEventListener('beforeunload', () => {
    if (voiceConverter) {
        voiceConverter.destroy();
    }
});

// ES6 모듈로 내보내기
export { VoiceConverter };