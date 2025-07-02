/**
 * 파일: services/webserver/src/static/js/voice_converter.js
 * 설명: 메인 VoiceConverter 클래스 (STT→TTS 파이프라인 지원)
 * 변경사항:
 * - STT + TTS 서버 연동
 * - 음성 → 텍스트 → 음성 변환 파이프라인
 * - TTS 처리 상태 추가
 * - 변환된 음성 재생 처리
 */
import { SessionManager } from './session_manager.js';
import { UIManager } from './ui_manager.js';

/**
 * 메인 VoiceConverter 클래스
 * STT→TTS 파이프라인을 통한 음성 변환 기능 제공
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
            this.uiManager.showToast('시스템 준비 완료! 음성 변환 서비스가 활성화되었습니다.', 'success');
            
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
        
        // STT 결과 수신 시 처리
        this.sessionManager.onSTTResult = (sessionId, sttResult) => {
            this.handleSTTResult(sessionId, sttResult);
        };
        
        // TTS 처리 상태 업데이트
        this.sessionManager.onTTSStatus = (sessionId, status) => {
            this.handleTTSStatus(sessionId, status);
        };
    }
    
    /**
     * 버튼 눌림 처리 - 음성 변환 녹음 시작
     */
    async handlePressStart() {
        console.log('🎤 음성 변환 녹음 시작');
        
        // 풀이 준비되지 않은 경우의 처리
        if (!this.isPoolReady) {
            // 즉시 녹음 상태로 보이게 하여 UX 향상
            this.uiManager.updateButtonState('recording');
            this.uiManager.showToast('시스템 준비 중... 잠시만 기다려주세요.', 'warning');
            
            // 최대 5초까지 기다림
            let waitTime = 0;
            const maxWait = 5000;
            const checkInterval = 100;
            
            while (!this.isPoolReady && waitTime < maxWait) {
                await new Promise(resolve => setTimeout(resolve, checkInterval));
                waitTime += checkInterval;
            }
            
            if (!this.isPoolReady) {
                this.uiManager.updateButtonState('ready');
                this.uiManager.showToast('시스템 준비에 시간이 오래 걸리고 있습니다. 잠시 후 다시 시도해주세요.', 'error');
                return;
            }
        }
        
        try {
            // 커넥션 가용성 확인
            if (!this.sessionManager.canStartNewRecording()) {
                this.uiManager.showToast('사용 가능한 커넥션이 없습니다.', 'warning');
                return;
            }
            
            // 녹음 시작
            this.uiManager.updateButtonState('recording');
            const sessionId = await this.sessionManager.startNewRecording();
            
            // UI 상태 업데이트
            this.uiManager.updateSystemStatus('stt', 'RECORDING');
            this.uiManager.updateSystemStatus('tts', 'IDLE');
            this.uiManager.showToast('🎤 음성 녹음 중... 말씀해주세요!', 'info');
            
            console.log(`⚡ 음성 변환 녹음 시작: ${sessionId}`);
            
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
     * 버튼 릴리즈 처리 - 녹음 중지 및 변환 시작
     */
    handlePressEnd() {
        console.log('🔽 음성 변환 녹음 완료 - STT→TTS 파이프라인 시작');
        
        this.sessionManager.stopCurrentSessionRecording();
        this.uiManager.updateButtonState('ready');
        this.uiManager.updateSystemStatus('stt', 'PROCESSING');
        this.uiManager.showToast('🔄 음성을 텍스트로 변환 중...', 'info');
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
                this.uiManager.updateSystemStatus('tts', 'IDLE');
                break;
                
            case 'recording':
                this.uiManager.updateButtonState('recording');
                this.uiManager.updateSystemStatus('stt', 'RECORDING');
                this.uiManager.updateSystemStatus('tts', 'IDLE');
                break;
                
            case 'processing':
                this.uiManager.updateButtonState('ready');
                this.uiManager.updateSystemStatus('stt', 'PROCESSING');
                this.uiManager.updateSystemStatus('tts', 'IDLE');
                break;
                
            case 'converting':
                this.uiManager.updateSystemStatus('stt', 'IDLE');
                this.uiManager.updateSystemStatus('tts', 'PROCESSING');
                break;
                
            case 'playing':
                this.uiManager.updateSystemStatus('stt', 'IDLE');
                this.uiManager.updateSystemStatus('tts', 'PLAYING');
                this.uiManager.showPlaybackIndicator(true);
                break;
                
            case 'completed':
                this.uiManager.updateSystemStatus('stt', 'IDLE');
                this.uiManager.updateSystemStatus('tts', 'IDLE');
                this.uiManager.showPlaybackIndicator(false);
                break;
                
            case 'error':
                this.uiManager.updateButtonState('ready');
                this.uiManager.updateSystemStatus('stt', 'ERROR');
                this.uiManager.updateSystemStatus('tts', 'ERROR');
                break;
        }
        
        // 전체 상태 업데이트
        this.updateOverallStatus();
    }
    
    /**
     * STT 결과 처리
     * @param {number} sessionId 
     * @param {Object} sttResult 
     */
    handleSTTResult(sessionId, sttResult) {
        if (sttResult && sttResult.transcription) {
            console.log(`📝 STT 결과 (세션: ${sessionId}): "${sttResult.transcription}"`);
            this.uiManager.showToast(`🎯 인식된 텍스트: "${sttResult.transcription}"`, 'success');
            this.uiManager.updateSystemStatus('stt', 'IDLE');
            this.uiManager.updateSystemStatus('tts', 'PROCESSING');
        } else {
            console.log(`❌ STT 실패 (세션: ${sessionId})`);
            this.uiManager.showToast('음성 인식에 실패했습니다.', 'error');
        }
    }
    
    /**
     * TTS 상태 처리
     * @param {number} sessionId 
     * @param {string} status 
     */
    handleTTSStatus(sessionId, status) {
        console.log(`🔊 TTS 상태 업데이트 (세션: ${sessionId}): ${status}`);
        
        switch (status) {
            case 'processing':
                this.uiManager.showToast('🔊 텍스트를 음성으로 변환 중...', 'info');
                this.uiManager.updateSystemStatus('tts', 'PROCESSING');
                break;
                
            case 'completed':
                this.uiManager.showToast('✅ 음성 변환 완료!', 'success');
                this.uiManager.updateSystemStatus('tts', 'PLAYING');
                break;
                
            case 'error':
                this.uiManager.showToast('❌ 음성 합성에 실패했습니다.', 'error');
                this.uiManager.updateSystemStatus('tts', 'ERROR');
                break;
        }
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
     * 변환된 오디오 수신 및 재생 처리
     * @param {number} sessionId 
     * @param {ArrayBuffer} audioData 
     */
    async handleAudioReceived(sessionId, audioData) {
        console.log(`🔊 변환된 음성 재생 시작 (세션: ${sessionId})`);
        
        try {
            // 재생 상태 업데이트
            this.uiManager.updateSystemStatus('tts', 'PLAYING');
            this.uiManager.showPlaybackIndicator(true);
            
            // 오디오 재생
            await this.uiManager.playAudio(audioData);
            console.log(`✅ 변환된 음성 재생 완료 (세션: ${sessionId})`);
            
            // 세션 완료 처리
            this.sessionManager.completeSession(sessionId);
            this.uiManager.showToast(`🎉 음성 변환 완료! (세션: ${sessionId})`, 'success');
            
            // 상태 초기화
            this.uiManager.updateSystemStatus('tts', 'IDLE');
            this.uiManager.showPlaybackIndicator(false);
            
        } catch (error) {
            console.error(`❌ 변환된 음성 재생 오류 (세션: ${sessionId}):`, error);
            this.sessionManager.handleSessionError(sessionId);
            this.uiManager.showToast('변환된 음성 재생 중 오류가 발생했습니다.', 'error');
            
            // 에러 상태 업데이트
            this.uiManager.updateSystemStatus('tts', 'ERROR');
            this.uiManager.showPlaybackIndicator(false);
        }
    }
    
    /**
     * 세션 에러 처리
     * @param {number} sessionId 
     */
    handleSessionError(sessionId) {
        console.error(`❌ 세션 에러 (세션: ${sessionId})`);
        this.uiManager.showToast(`세션 ${sessionId}에서 오류가 발생했습니다.`, 'error');
        
        // 에러 상태로 UI 업데이트
        this.uiManager.updateSystemStatus('stt', 'ERROR');
        this.uiManager.updateSystemStatus('tts', 'ERROR');
        this.uiManager.showPlaybackIndicator(false);
    }
    
    /**
     * 전체 상태 업데이트
     */
    updateOverallStatus() {
        const playingCount = this.sessionManager.getSessionCountByStatus('playing');
        const processingCount = this.sessionManager.getSessionCountByStatus('processing');
        const convertingCount = this.sessionManager.getSessionCountByStatus('converting');
        
        // 재생 인디케이터 업데이트
        this.uiManager.showPlaybackIndicator(playingCount > 0);
        
        // 로그 출력
        const totalSessions = this.sessionManager.getActiveSessionCount();
        const poolStatus = this.sessionManager.getPoolStatus();
        console.log(`📊 상태 업데이트 - 총 세션: ${totalSessions}, 재생중: ${playingCount}, STT 처리중: ${processingCount}, TTS 변환중: ${convertingCount}, 풀 상태: ${poolStatus.available}/${poolStatus.total}`);
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
            uiConnected: this.uiManager.isConnected,
            pipeline: 'STT→TTS'  // 파이프라인 정보 추가
        };
    }
}

// 전역 변수로 인스턴스 저장 (디버깅용)
let voiceConverter;

// 페이지 로드 시 초기화
document.addEventListener('DOMContentLoaded', () => {
    console.log('📄 DOM 로드 완료, VoiceConverter (STT→TTS) 초기화...');
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