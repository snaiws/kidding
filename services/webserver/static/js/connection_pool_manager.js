/**
 * 파일: frontend/js/connection_pool_manager.js
 * 설명: 커넥션 풀을 관리하는 클래스
 * 기능: 미리 연결된 WebSocket들을 관리하고 필요시 할당/반환
 */
class ConnectionPoolManager {
    constructor(poolSize = 3) {
        this.poolSize = poolSize;
        this.availableConnections = [];
        this.busyConnections = new Map(); // sessionId -> connection
        this.initializingConnections = new Set();
        this.isInitialized = false;
        
        // 이벤트 핸들러들
        this.onConnectionReady = null;
        this.onConnectionError = null;
        this.onPoolStatusChange = null;
    }
    
    /**
     * 커넥션 풀 초기화
     */
    async initialize() {
        console.log(`🏊 커넥션 풀 초기화 시작 (크기: ${this.poolSize})`);
        
        const initPromises = [];
        for (let i = 0; i < this.poolSize; i++) {
            initPromises.push(this.createConnection(i));
        }
        
        try {
            await Promise.all(initPromises);
            this.isInitialized = true;
            console.log('✅ 커넥션 풀 초기화 완료');
            this.notifyPoolStatusChange();
        } catch (error) {
            console.error('❌ 커넥션 풀 초기화 실패:', error);
            throw error;
        }
    }
    
    /**
     * 새 커넥션 생성
     * @param {number} index 
     */
    async createConnection(index) {
        const connectionId = `pool_${index}_${Date.now()}`;
        this.initializingConnections.add(connectionId);
        
        return new Promise((resolve, reject) => {
            try {
                const ws = new WebSocket('ws://localhost:8000/ws/audio');
                ws.binaryType = 'arraybuffer';
                
                const connection = {
                    id: connectionId,
                    websocket: ws,
                    isAvailable: false,
                    createdAt: Date.now(),
                    sessionId: null
                };
                
                ws.onopen = () => {
                    console.log(`✅ 커넥션 생성됨: ${connectionId}`);
                    connection.isAvailable = true;
                    this.initializingConnections.delete(connectionId);
                    this.availableConnections.push(connection);
                    this.notifyPoolStatusChange();
                    resolve(connection);
                };
                
                ws.onerror = (error) => {
                    console.error(`❌ 커넥션 생성 실패: ${connectionId}`, error);
                    this.initializingConnections.delete(connectionId);
                    this.notifyPoolStatusChange();
                    reject(error);
                };
                
                ws.onclose = () => {
                    console.log(`🔌 커넥션 종료됨: ${connectionId}`);
                    this.handleConnectionClose(connection);
                };
                
            } catch (error) {
                this.initializingConnections.delete(connectionId);
                reject(error);
            }
        });
    }
    
    /**
     * 사용 가능한 커넥션 가져오기
     * @returns {Object|null} 커넥션 객체 또는 null
     */
    getAvailableConnection() {
        if (this.availableConnections.length === 0) {
            console.warn('⚠️ 사용 가능한 커넥션이 없습니다');
            return null;
        }
        
        const connection = this.availableConnections.shift();
        connection.isAvailable = false;
        
        console.log(`📤 커넥션 할당됨: ${connection.id}`);
        this.notifyPoolStatusChange();
        return connection;
    }
    
    /**
     * 커넥션을 세션에 할당
     * @param {string} sessionId 
     * @returns {Object|null} 할당된 커넥션 또는 null
     */
    assignConnectionToSession(sessionId) {
        const connection = this.getAvailableConnection();
        if (!connection) {
            return null;
        }
        
        connection.sessionId = sessionId;
        this.busyConnections.set(sessionId, connection);
        
        console.log(`🔗 세션에 커넥션 할당: ${sessionId} -> ${connection.id}`);
        return connection;
    }
    
    /**
     * 커넥션을 풀로 반환 (재사용)
     * @param {string} sessionId 
     */
    releaseConnection(sessionId) {
        const connection = this.busyConnections.get(sessionId);
        if (!connection) {
            console.warn(`⚠️ 세션 ${sessionId}의 커넥션을 찾을 수 없습니다`);
            return;
        }
        
        this.busyConnections.delete(sessionId);
        connection.sessionId = null;
        connection.isAvailable = true;
        this.availableConnections.push(connection);
        
        console.log(`📥 커넥션 반환됨: ${connection.id} (세션: ${sessionId})`);
        this.notifyPoolStatusChange();
    }
    
    /**
     * 커넥션 종료 처리 및 새 커넥션 생성
     * @param {Object} connection 
     */
    async handleConnectionClose(connection) {
        // busy 목록에서 제거
        for (const [sessionId, conn] of this.busyConnections) {
            if (conn.id === connection.id) {
                this.busyConnections.delete(sessionId);
                console.log(`🔌 종료된 커넥션의 세션 정리: ${sessionId}`);
                break;
            }
        }
        
        // available 목록에서 제거
        const availableIndex = this.availableConnections.findIndex(conn => conn.id === connection.id);
        if (availableIndex !== -1) {
            this.availableConnections.splice(availableIndex, 1);
        }
        
        // 새 커넥션 생성으로 풀 크기 유지
        try {
            const newConnection = await this.createConnection(Date.now());
            console.log(`🔄 커넥션 교체 완료: ${connection.id} -> ${newConnection.id}`);
        } catch (error) {
            console.error('❌ 커넥션 교체 실패:', error);
            this.notifyPoolStatusChange();
        }
    }
    
    /**
     * 특정 세션의 커넥션 가져오기
     * @param {string} sessionId 
     * @returns {Object|null}
     */
    getConnectionBySession(sessionId) {
        return this.busyConnections.get(sessionId) || null;
    }
    
    /**
     * 풀 상태 정보 반환
     * @returns {Object}
     */
    getPoolStatus() {
        return {
            total: this.poolSize,
            available: this.availableConnections.length,
            busy: this.busyConnections.size,
            initializing: this.initializingConnections.size,
            isInitialized: this.isInitialized,
            canAcceptNewSession: this.availableConnections.length > 0
        };
    }
    
    /**
     * 풀 상태 변경 알림
     */
    notifyPoolStatusChange() {
        if (this.onPoolStatusChange) {
            this.onPoolStatusChange(this.getPoolStatus());
        }
    }
    
    /**
     * 모든 커넥션 정리
     */
    destroy() {
        console.log('🧹 커넥션 풀 정리 중...');
        
        // 모든 사용중인 커넥션 종료
        for (const connection of this.busyConnections.values()) {
            if (connection.websocket.readyState === WebSocket.OPEN) {
                connection.websocket.close();
            }
        }
        
        // 모든 사용 가능한 커넥션 종료
        for (const connection of this.availableConnections) {
            if (connection.websocket.readyState === WebSocket.OPEN) {
                connection.websocket.close();
            }
        }
        
        this.busyConnections.clear();
        this.availableConnections = [];
        this.initializingConnections.clear();
        this.isInitialized = false;
        
        console.log('✅ 커넥션 풀 정리 완료');
    }
}

export { ConnectionPoolManager };