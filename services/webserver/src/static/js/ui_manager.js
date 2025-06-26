/**
 * 파일: frontend/js/ui_manager.js
 * 설명: UI 상태 관리 및 업데이트를 담당하는 클래스 (업데이트됨)
 * 변경사항:
 * - 고정 버튼 크기 지원
 * - 커넥션 풀 상태 표시 기능 추가
 * - connecting 상태 제거, ready/recording/disabled 상태만 사용
 * - 풀 고갈 시 버튼 자동 비활성화
 */
class UIManager {
    constructor() {
        this.elements = this.initElements();
        this.startTime = Date.now();
        this.statusWS = null;
        this.isConnected = false;
        
        this.startUptimeTimer();
        this.connectStatusWebSocket();
    }
    
    /**
     * DOM 요소들을 초기화하고 참조를 저장
     */
    initElements() {
        return {
            voiceBtn: document.getElementById('voiceBtn'),
            buttonText: document.querySelector('.button-text'),
            buttonWave: document.getElementById('buttonWaveAnimation'),
            connectionStatus: document.getElementById('connectionStatus'),
            playbackIndicator: document.getElementById('playbackIndicator'),
            mainStatusIndicator: document.getElementById('mainStatusIndicator'),
            websocketStatus: document.getElementById('websocketStatus'),
            sttStatus: document.getElementById('sttStatus'),
            voiceStatus: document.getElementById('voiceStatus'),
            ttsStatus: document.getElementById('ttsStatus'),
            connCount: document.getElementById('connCount'),
            uptime: document.getElementById('uptime'),
            poolAvailable: document.getElementById('poolAvailable'),
            poolBusy: document.getElementById('poolBusy')
        };
    }
    
    /**
     * 버튼 상태 업데이트
     * @param {string} state - ready, recording, disabled
     */
    updateButtonState(state) {
        const { voiceBtn, buttonText, buttonWave } = this.elements;
        
        // 기존 클래스 제거
        voiceBtn.className = '';
        buttonWave.classList.remove('active');
        
        switch (state) {
            case 'ready':
                voiceBtn.disabled = false;
                buttonText.textContent = 'Press to doubt';
                break;
                
            case 'recording':
                voiceBtn.disabled = false;
                voiceBtn.classList.add('recording');
                buttonText.textContent = 'Recording...';
                buttonWave.classList.add('active');
                break;
                
            case 'disabled':
                voiceBtn.disabled = true;
                voiceBtn.classList.add('disabled');
                buttonText.textContent = 'Pool exhausted';
                break;
        }
    }
    
    /**
     * 시스템 상태 업데이트
     * @param {string} component - websocket, stt, voice, tts
     * @param {string} status - 상태 문자열
     */
    updateSystemStatus(component, status) {
        const statusMap = {
            'websocket': 'websocketStatus',
            'stt': 'sttStatus',
            'voice': 'voiceStatus',
            'tts': 'ttsStatus'
        };
        
        const elementKey = statusMap[component];
        if (elementKey && this.elements[elementKey]) {
            const element = this.elements[elementKey];
            element.textContent = status;
            element.className = 'status-value';
            
            // 상태별 스타일 적용
            if (status === 'ERROR' || status === 'DISCONNECTED') {
                element.classList.add('error');
            } else if (status.includes('PROCESSING') || status.includes('CONVERTING') || status.includes('PLAYING') || status.includes('RECORDING')) {
                element.classList.add('processing');
            } else if (status === 'CONNECTING' || status === 'PAUSED') {
                element.classList.add('warning');
            }
        }
        
        this.updateMainStatusIndicator();
    }
    
    /**
     * 커넥션 풀 상태 업데이트
     * @param {Object} poolStatus 
     */
    updatePoolStatus(poolStatus) {
        const { poolAvailable, poolBusy } = this.elements;
        
        if (poolAvailable) {
            poolAvailable.textContent = poolStatus.available.toString();
        }
        
        if (poolBusy) {
            poolBusy.textContent = poolStatus.busy.toString();
        }
        
        // 풀이 고갈되면 버튼 비활성화
        if (!poolStatus.canAcceptNewSession) {
            this.updateButtonState('disabled');
        } else if (this.elements.voiceBtn.disabled && !this.elements.voiceBtn.classList.contains('recording')) {
            this.updateButtonState('ready');
        }
    }
    
    /**
     * 메인 상태 인디케이터 업데이트
     */
    updateMainStatusIndicator() {
        const { mainStatusIndicator } = this.elements;
        const hasError = document.querySelector('.status-value.error');
        const hasProcessing = document.querySelector('.status-value.processing');
        
        if (hasError) {
            mainStatusIndicator.className = 'status-indicator disconnected';
        } else if (hasProcessing) {
            mainStatusIndicator.className = 'status-indicator processing';
        } else if (this.isConnected) {
            mainStatusIndicator.className = 'status-indicator connected';
        } else {
            mainStatusIndicator.className = 'status-indicator disconnected';
        }
    }
    
    /**
     * 연결 상태 업데이트
     * @param {boolean} connected 
     */
    updateConnectionStatus(connected) {
        const { connectionStatus } = this.elements;
        this.isConnected = connected;
        
        if (connected) {
            connectionStatus.classList.add('connected');
        } else {
            connectionStatus.classList.remove('connected');
        }
    }
    
    /**
     * 연결 수 업데이트
     * @param {number} count 
     */
    updateConnectionCount(count) {
        const { connCount } = this.elements;
        if (connCount) {
            connCount.textContent = count.toString();
        }
    }
    
    /**
     * 재생 인디케이터 표시/숨김
     * @param {boolean} show 
     */
    showPlaybackIndicator(show) {
        const { playbackIndicator } = this.elements;
        if (show) {
            playbackIndicator.classList.add('active');
        } else {
            playbackIndicator.classList.remove('active');
        }
    }
    
    /**
     * 토스트 알림 표시
     * @param {string} message 
     * @param {string} type - success, error, warning
     */
    showToast(message, type = 'success') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        document.body.appendChild(toast);
        
        // 애니메이션 처리
        setTimeout(() => toast.classList.add('show'), 100);
        setTimeout(() => {
            toast.classList.remove('show');
            setTimeout(() => {
                if (document.body.contains(toast)) {
                    document.body.removeChild(toast);
                }
            }, 300);
        }, 3000);
    }
    
    /**
     * 상태 WebSocket 연결
     */
    connectStatusWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        this.statusWS = new WebSocket(`${protocol}//${window.location.host}/ws/status`);
        
        this.statusWS.onopen = () => {
            this.updateConnectionStatus(true);
            this.updateSystemStatus('websocket', 'CONNECTED');
            console.log('✅ 상태 WebSocket 연결됨');
        };
        
        this.statusWS.onclose = () => {
            this.updateConnectionStatus(false);
            this.updateSystemStatus('websocket', 'DISCONNECTED');
            console.log('❌ 상태 WebSocket 연결 끊어짐');
            
            // 자동 재연결 시도 (5초 후)
            setTimeout(() => {
                if (this.statusWS.readyState === WebSocket.CLOSED) {
                    console.log('🔄 상태 WebSocket 재연결 시도...');
                    this.connectStatusWebSocket();
                }
            }, 5000);
        };
        
        this.statusWS.onerror = (error) => {
            this.updateConnectionStatus(false);
            this.updateSystemStatus('websocket', 'ERROR');
            console.error('❌ 상태 WebSocket 오류:', error);
        };
        
        this.statusWS.onmessage = (event) => {
            try {
                const status = JSON.parse(event.data);
                this.handleStatusMessage(status);
            } catch (error) {
                console.error('❌ 상태 메시지 파싱 오류:', error);
            }
        };
    }
    
    /**
     * 서버 상태 메시지 처리
     * @param {Object} status 
     */
    handleStatusMessage(status) {
        if (status.type === 'status') {
            // 서버에서 제공하는 추가 상태 정보 처리
            console.log('📊 서버 상태:', status);
        }
    }
    
    /**
     * 업타임 타이머 시작
     */
    startUptimeTimer() {
        setInterval(() => {
            const uptime = Date.now() - this.startTime;
            const hours = Math.floor(uptime / 3600000);
            const minutes = Math.floor((uptime % 3600000) / 60000);
            const seconds = Math.floor((uptime % 60000) / 1000);
            
            const uptimeStr = `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            
            const { uptime: uptimeElement } = this.elements;
            if (uptimeElement) {
                uptimeElement.textContent = uptimeStr;
            }
        }, 1000);
    }
    
    /**
     * 오디오 재생
     * @param {ArrayBuffer} audioData 
     * @returns {Promise}
     */
    async playAudio(audioData) {
        return new Promise((resolve, reject) => {
            try {
                const audioBlob = new Blob([audioData], { type: 'audio/wav' });
                const audioUrl = URL.createObjectURL(audioBlob);
                const audio = new Audio(audioUrl);
                
                audio.onended = () => {
                    URL.revokeObjectURL(audioUrl);
                    resolve();
                };
                
                audio.onerror = (error) => {
                    URL.revokeObjectURL(audioUrl);
                    reject(error);
                };
                
                audio.play().catch(reject);
                
            } catch (error) {
                reject(error);
            }
        });
    }
    
    /**
     * UI 정리 (필요시)
     */
    destroy() {
        if (this.statusWS) {
            this.statusWS.close();
        }
    }
}

export { UIManager };