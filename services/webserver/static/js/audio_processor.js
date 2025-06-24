/**
 * 오디오 처리를 담당하는 클래스
 * 마이크 입력을 받아 실시간으로 PCM 데이터를 콜백으로 전달
 */
class AudioProcessor {
    constructor() {
        this.stream = null;
        this.audioContext = null;
        this.mediaStreamSource = null;
        this.processor = null;
        this.isActive = false;
    }
    
    /**
     * 오디오 프로세싱 시작
     * @param {Function} onDataCallback - PCM 데이터를 받을 콜백 함수
     */
    async start(onDataCallback) {
        try {
            console.log('🎤 마이크 스트림 요청...');
            
            this.stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 16000
                } 
            });
            
            console.log('✅ 마이크 스트림 획득됨');
            
            this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
                sampleRate: 16000
            });
            
            this.mediaStreamSource = this.audioContext.createMediaStreamSource(this.stream);
            
            // AudioWorklet 우선 시도, 실패 시 ScriptProcessor로 fallback
            if (this.audioContext.audioWorklet) {
                await this.setupAudioWorklet(onDataCallback);
            } else {
                this.setupScriptProcessor(onDataCallback);
            }
            
            this.onDataCallback = onDataCallback;
            this.isActive = true;
            
            console.log('✅ 오디오 프로세싱 시작됨');
            
        } catch (error) {
            console.error('❌ AudioProcessor 시작 오류:', error);
            throw new Error('마이크 접근 권한이 필요합니다.');
        }
    }
    
    /**
     * AudioWorklet을 사용한 오디오 처리 설정
     * @param {Function} onDataCallback 
     */
    async setupAudioWorklet(onDataCallback) {
        try {
            const workletCode = `
                class AudioCaptureProcessor extends AudioWorkletProcessor {
                    process(inputs, outputs, parameters) {
                        const input = inputs[0];
                        if (input && input[0]) {
                            const audioData = input[0];
                            this.port.postMessage(audioData);
                        }
                        return true;
                    }
                }
                registerProcessor('audio-capture-processor', AudioCaptureProcessor);
            `;
            
            const blob = new Blob([workletCode], { type: 'application/javascript' });
            const workletUrl = URL.createObjectURL(blob);
            
            await this.audioContext.audioWorklet.addModule(workletUrl);
            
            this.processor = new AudioWorkletNode(this.audioContext, 'audio-capture-processor');
            this.processor.port.onmessage = (event) => {
                if (this.isActive && onDataCallback) {
                    onDataCallback(event.data);
                }
            };
            
            this.mediaStreamSource.connect(this.processor);
            
            URL.revokeObjectURL(workletUrl);
            
        } catch (error) {
            console.warn('AudioWorklet 실패, ScriptProcessor로 fallback:', error);
            this.setupScriptProcessor(onDataCallback);
        }
    }
    
    /**
     * ScriptProcessor를 사용한 오디오 처리 설정 (fallback)
     * @param {Function} onDataCallback 
     */
    setupScriptProcessor(onDataCallback) {
        this.processor = this.audioContext.createScriptProcessor(4096, 1, 1);
        
        this.processor.onaudioprocess = (event) => {
            if (this.isActive && onDataCallback) {
                const audioData = event.inputBuffer.getChannelData(0);
                onDataCallback(new Float32Array(audioData));
            }
        };
        
        this.mediaStreamSource.connect(this.processor);
        this.processor.connect(this.audioContext.destination);
    }
    
    /**
     * 오디오 프로세싱 중지 및 리소스 정리
     */
    stop() {
        console.log('🛑 AudioProcessor 중지...');
        
        this.isActive = false;
        
        if (this.processor) {
            this.processor.disconnect();
            this.processor = null;
        }
        
        if (this.mediaStreamSource) {
            this.mediaStreamSource.disconnect();
            this.mediaStreamSource = null;
        }
        
        if (this.audioContext) {
            this.audioContext.close();
            this.audioContext = null;
        }
        
        if (this.stream) {
            this.stream.getTracks().forEach(track => {
                track.stop();
                console.log('🎤 마이크 트랙 중지됨');
            });
            this.stream = null;
        }
        
        console.log('✅ AudioProcessor 완전히 중지됨');
    }
}

// ES6 모듈로 내보내기
export { AudioProcessor };