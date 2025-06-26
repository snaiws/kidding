/**
 * 파일: services/webserver/src/static/js/voice_converter.js
 * 설명: 메인 VoiceConverter 클래스 (업데이트됨)
 * 변경사항:
 * - 진짜 0초 connection을 위해 페이지 로드 즉시 커넥션 풀 백그라운드 초기화
 * - 사용자는 대기 없이 즉시 버튼 사용 가능
 * - connecting 단계 완전 제거
 * - 실제 WebSocket 연결은 백그라운드에서 미리 완료
 */
import { SessionManager } from './session_manager.js';
import { UIManager } from './ui_manager.js';

/**
 * 메인 VoiceConverter 클래스
 * 커넥션 풀을 사용한 세션 관리와 UI 관리를 통합하여 전체 애플리케이션을 제어
 */
class VoiceConverter {
    constructor() {
        console.log('🚀 VoiceConverter 초기화 시작...');
        
        // 모듈 초기화
        this.sessionManager = new SessionManager();
        this.uiManager = new UIManager();
        this.isPoolReady = false;
        
        // 이벤트 핸들러는 즉시 바인딩
        this.bindEvents();
        this.setupEventHandlers();
        
        // 사용자에게는 즉시 준비된 것처럼 보이게 함
        this.uiManager.updateButtonState('ready');
        
        // 백그라운드에서 커넥션 풀 준비 (사용자 대기 없음)
        this.initializeConnectionPoolBackground();
        
        console.log('✅ VoiceConverter UI 준비 완료 (커넥션 풀은 백그라운드에서 준비 중)');
    }
    
    /**
     * 백그라운드에서 커넥션 풀 초기화 (사용자 대기 없음)
     */
    async initializeConnectionPoolBackground() {
        try {
            console.log('🏊 백그라운드에서 커넥션 풀 준비 중... (사용자는 즉시 사용 가능)');
            
            // 백그라운드에서 실행 (사용자는 기다리지 않음)
            await this.sessionManager.initialize();
            
            this.isPoolReady = true;
            console.log('✅ 커넥션 풀 준비 완료 - 이제 정말 0초 connection!');
            
            // 풀이 준비되면 상태 업데이트
            this.uiManager.showToast('시스템 준비 완료! 이제 즉시 녹음 가능합니다.', 'success');
            
        } catch (error) {
            console.error('❌ 커넥션 풀 준비 실패:', error);
            this.uiManager.updateButtonState('disabled');
            this.uiManager.showToast('시스템 초기화에 실패했습니다.', 'error');
        }
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
            if (!isPressed && !voiceBtn.disabled) {
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
            if (!isPressed && !voiceBtn.disabled) {
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
        
        // 커넥션 풀 상태 변경 시 UI 업데이트
        this.sessionManager.onPoolStatusChange = (poolStatus) => {
            this.handlePoolStatusChange(poolStatus);
        };
    }
    
    /**
     * 버튼 눌림 처리 - 진짜 0초 connection (이미 연결된 커넥션 사용)
     */
    async handlePressStart() {
        console.log('🎤 버튼 눌림 감지');
        
        // 풀이 준비되지 않은 경우의 처리
        if (!this.isPoolReady) {
            // 즉시 녹음 상태로 보이게 하여 UX 향상
            this.uiManager.updateButtonState('recording');
            this.uiManager.showToast('커넥션 준비 중... 잠시만 기다려주세요.', 'warning');
            
            // 최대 5초까지 기다림 (일반적으로 1-2초면 충분)
            let waitTime = 0;
            const maxWait = 5000;
            const checkInterval = 100;
            
            while (!this.isPoolReady && waitTime < maxWait) {
                await new Promise(resolve => setTimeout(resolve, checkInterval));
                waitTime += checkInterval;
            }
            
            if (!this.isPoolReady) {
                this.uiManager.updateButtonState('ready');
                this.uiManager.showToast('커넥션 준비에 시간이 오래 걸리고 있습니다. 잠시 후 다시 시도해주세요.', 'error');
                return;
            }
        }
        
        try {
            // 이미 연결된 커넥션 확인 (즉시 확인 가능)
            if (!this.sessionManager.canStartNewRecording()) {
                this.uiManager.showToast('사용 가능한 커넥션이 없습니다.', 'warning');
                return;
            }
            
            // 🚀 여기서 진짜 0초 connection! (이미 연결된 WebSocket 사용)
            this.uiManager.updateButtonState('recording');
            const sessionId = await this.sessionManager.startNewRecording();
            
            console.log(`⚡ 0초 connection 녹음 시작 완료: ${sessionId}`);
            
        } catch (error) {
            console.error('❌ 녹음 시작 오류:', error);
            this.uiManager.updateButtonState('ready');
            this.uiManager.updateSystemStatus('stt', 'ERROR');
            
            if (error.message.includes('사용 가능한 커넥션이 없습니다')) {
                this.uiManager.showToast('모든 커넥션이 사용 중입니다. 잠시 후 다시 시도해주세요.', 'warning');
            } else {
                this.uiManager.showToast('녹음 시작 중 오류가 발생했습니다.', 'error');
            }
        }
    }
    
    /**
     * 버튼 릴리즈 처리 - 녹음 중지
     */
    handlePressEnd() {
        console.log('🔽 버튼 릴리즈 감지 - 녹음 중지');
        
        this.sessionManager.stopCurrentSessionRecording();
        this.uiManager.updateButtonState('ready');
        this.uiManager.updateSystemStatus('stt', 'IDLE');
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
            case 'ready':
                this.uiManager.updateSystemStatus('stt', 'IDLE');
                break;
                
            case 'recording':
                this.uiManager.updateButtonState('recording');
                this.uiManager.updateSystemStatus('stt', 'RECORDING');
                this.uiManager.updateSystemStatus('voice', 'IDLE');
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
     * 커넥션 풀 상태 변경 처리
     * @param {Object} poolStatus 
     */
    handlePoolStatusChange(poolStatus) {
        this.uiManager.updatePoolStatus(poolStatus);
        
        // 풀 상태 로깅
        console.log(`🏊 풀 상태: 사용가능=${poolStatus.available}, 사용중=${poolStatus.busy}, 총=${poolStatus.total}`);
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
        const poolStatus = this.sessionManager.getPoolStatus();
        console.log(`📊 상태 업데이트 - 총 세션: ${totalSessions}, 재생중: ${playingCount}, 처리중: ${processingCount}, 풀 상태: ${poolStatus.available}/${poolStatus.total}`);
    }
    
    /**
     * 애플리케이션 종료 시 정리
     */
    destroy() {
        console.log('🧹 VoiceConverter 정리 중...');
        
        // 세션 매니저 정리 (커넥션 풀 포함)
        this.sessionManager.destroy();
        
        // UI 정리
        this.uiManager.destroy();
        
        this.isInitialized = false;
        console.log('✅ VoiceConverter 정리 완료');
    }
    
    /**
     * 디버그 정보 출력
     */
    getDebugInfo() {
        // 디버그 정보에 풀 준비 상태 추가
        return {
            isPoolReady: this.isPoolReady,
            activeSessions: this.sessionManager.getActiveSessionCount(),
            currentSession: this.sessionManager.currentSession,
            poolStatus: this.sessionManager.getPoolStatus(),
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