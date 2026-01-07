/**
 * Hybrid Voice Satellite Client
 * Browser-based voice control with wake word detection
 */

// Configuration
const CONFIG = {
    // Dynamically determine WebSocket URL based on current location
    wsUrl: localStorage.getItem('wsUrl') || 
           ((window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host),
    wakeWord: localStorage.getItem('wakeWord') || 'alexa_v0.1',
    authToken: localStorage.getItem('authToken') || 'change-me-in-production',
    overlayUrl: localStorage.getItem('overlayUrl') || '',
    sampleRate: 16000,
    ttsSampleRate: 16000,
    channels: 1
};

// Application state
const STATE = {
    ws: null,
    audioContext: null,
    mediaStream: null,
    audioWorkletNode: null,
    isActive: false,
    isListening: false,
    reconnectAttempts: 0,
    maxReconnectAttempts: 5,
    onnxSessions: {
        mel: null,
        embedding: null,
        wakeWord: null
    },
    buffers: {
        mel: [], // Grows/splices dynamically
        emb: new Array(16).fill(0).map(() => new Float32Array(96).fill(0)) // Fixed ring buffer
    },
    lastError: null
};

// DOM Elements
const elements = {
    activateBtn: document.getElementById('activate-btn'),
    settingsBtn: document.getElementById('settings-btn'),
    settingsPanel: document.getElementById('settings-panel'),
    saveSettings: document.getElementById('save-settings'),
    clearLogBtn: document.getElementById('clear-log-btn'),
    wsStatus: document.getElementById('ws-status'),
    wyomingStatus: document.getElementById('wyoming-status'),
    micStatus: document.getElementById('mic-status'),
    stateText: document.getElementById('state-text'),
    micVisualizer: document.getElementById('mic-visualizer'),
    debugLog: document.getElementById('debug-log'),
    wsUrlInput: document.getElementById('ws-url'),
    wakeWordSelect: document.getElementById('wake-word-select'),
    wakeWordSelect: document.getElementById('wake-word-select'),
    wakeWordSelect: document.getElementById('wake-word-select'),
    authTokenInput: document.getElementById('auth-token'),
    overlayUrlInput: document.getElementById('overlay-url-input'),
    // Overlay specific
    iframe: document.getElementById('overlay-iframe'),
    activateFab: document.getElementById('activate-fab'),
    fabVisualizer: document.getElementById('fab-visualizer'),
    connectionStatus: document.getElementById('connection-status'),
    textBubble: document.getElementById('text-bubble'),
    bubbleText: document.getElementById('bubble-text')
};

/**
 * Initialize the application
 */
async function init() {
    log('Application starting...', 'info');
    
    // Load saved settings
    elements.wsUrlInput.value = CONFIG.wsUrl;
    elements.wakeWordSelect.value = CONFIG.wakeWord;
    elements.wsUrlInput.value = CONFIG.wsUrl;
    elements.wakeWordSelect.value = CONFIG.wakeWord;
    elements.authTokenInput.value = CONFIG.authToken;
    if (elements.overlayUrlInput) elements.overlayUrlInput.value = CONFIG.overlayUrl;

    // Set initial iframe URL if configured locally
    if (CONFIG.overlayUrl && elements.iframe) {
        elements.iframe.src = CONFIG.overlayUrl;
        log(`Loaded local overlay URL: ${CONFIG.overlayUrl}`, 'info');
    }
    
    // Setup event listeners
    // Setup event listeners
    if (elements.activateBtn) {
        elements.activateBtn.addEventListener('click', toggleActivation);
    }
    if (elements.activateFab) {
        elements.activateFab.addEventListener('click', toggleActivation);
    }
    
    if (elements.settingsBtn) elements.settingsBtn.addEventListener('click', toggleSettings);
    if (elements.saveSettings) elements.saveSettings.addEventListener('click', saveSettings);
    if (elements.clearLogBtn) elements.clearLogBtn.addEventListener('click', clearLog);
    
    // Auto-connect to WebSocket for config/status
    connectWebSocket().catch(err => log(`Auto-connect failed: ${err.message}`, 'warning'));
    
    log('Application initialized', 'success');
}

/**
 * Toggle voice control activation
 */
async function toggleActivation() {
    if (!STATE.isActive) {
        await activate();
    } else {
        await deactivate();
    }
}

/**
 * Activate voice control
 */
async function activate() {
    try {
        log('Activating voice control...', 'info');
        
        // Initialize Audio Context
        await initAudioContext();
        
        // Ensure WebSocket is connected
        if (!STATE.ws || STATE.ws.readyState !== WebSocket.OPEN) {
             await connectWebSocket();
        }
        
        // Request microphone access
        await requestMicrophone();
        
        // Load wake word model
        await loadWakeWordModel();
        
        STATE.isActive = true;
        updateUI();
        
        if (elements.activateBtn) {
            elements.activateBtn.innerHTML = '<span>Deactivate</span>';
            elements.activateBtn.classList.add('active');
        }
        if (elements.activateFab) {
            elements.activateFab.classList.add('active');
        }
        
        log('Voice control activated', 'success');
        
    } catch (error) {
        log(`Activation failed: ${error.message}`, 'error');
        await deactivate();
    }
}

/**
 * Deactivate voice control
 */
async function deactivate() {
    log('Deactivating voice control...', 'info');
    
    if (STATE.audioWorkletNode) {
        STATE.audioWorkletNode.disconnect();
        STATE.audioWorkletNode = null;
    }
    
    if (STATE.mediaStream) {
        STATE.mediaStream.getTracks().forEach(track => track.stop());
        STATE.mediaStream = null;
    }
    
    if (STATE.audioContext) {
        await STATE.audioContext.close();
        STATE.audioContext = null;
    }
    
    // Do not close WebSocket to keep config/overlay active
    // if (STATE.ws) {
    //    STATE.ws.close();
    //    STATE.ws = null;
    // }
    
    STATE.isActive = false;
    STATE.isListening = false;
    
    updateUI();
    
    if (elements.activateBtn) {
        elements.activateBtn.innerHTML = '<span>Activate Voice Control</span>';
        elements.activateBtn.classList.remove('active');
    }
    if (elements.activateFab) {
        elements.activateFab.classList.remove('active');
        elements.activateFab.classList.remove('listening');
    }
    
    log('Voice control deactivated', 'info');
}

/**
 * Initialize Web Audio Context
 */
async function initAudioContext() {
    if (!STATE.audioContext) {
        STATE.audioContext = new (window.AudioContext || window.webkitAudioContext)();

        log(`Audio context initialized at ${STATE.audioContext.sampleRate}Hz`, 'info');
        
        if (STATE.audioContext.sampleRate !== 16000) {
             const msg = `Sample rate is ${STATE.audioContext.sampleRate}Hz. Resampling will be active.`;
             log(msg, 'warning');
             console.warn(msg);
        }
        console.log(`[DEBUG] AudioContext sample rate: ${STATE.audioContext.sampleRate} Hz`);
        
        if (STATE.audioContext.sampleRate !== 16000) {
             console.warn(`[WARNING] AudioContext is running at ${STATE.audioContext.sampleRate}Hz instead of 16000Hz. Detection will degrade.`);
        }
    }
    
    if (STATE.audioContext.state === 'suspended') {
        await STATE.audioContext.resume();
    }
}

/**
 * Connect to WebSocket server
 */
function connectWebSocket() {
    return new Promise((resolve, reject) => {
        log(`Connecting to ${CONFIG.wsUrl}...`, 'info');
        
        STATE.ws = new WebSocket(CONFIG.wsUrl);
        
        STATE.ws.onopen = async () => {
            log('WebSocket connected', 'success');
            updateStatus('ws-status', 'connected', 'Connected');
            
            // Authenticate if token is set
            if (CONFIG.authToken) {
                STATE.ws.send(JSON.stringify({
                    type: 'auth',
                    token: CONFIG.authToken
                }));
            }

            // Request initial status and config
            STATE.ws.send(JSON.stringify({ type: 'status_request' }));
            
            STATE.reconnectAttempts = 0;
            resolve();
        };
        
        STATE.ws.onclose = () => {
            log('WebSocket disconnected', 'warning');
            updateStatus('ws-status', 'disconnected', 'Disconnected');
            
            // Attempt reconnection (Infinite with backoff cap)
            if (STATE.isActive) {
                STATE.reconnectAttempts++;
                const delay = Math.min(2000 * STATE.reconnectAttempts, 10000); // Cap at 10s
                log(`Reconnecting in ${delay/1000}s...`, 'info');
                setTimeout(() => connectWebSocket(), delay);
            }
        };
        
        STATE.ws.onerror = (error) => {
            log(`WebSocket error: ${error}`, 'error');
            reject(new Error('WebSocket connection failed'));
        };
        
        STATE.ws.onmessage = handleWebSocketMessage;
        
        // Timeout after 5 seconds
        setTimeout(() => {
            if (STATE.ws.readyState !== WebSocket.OPEN) {
                reject(new Error('Connection timeout'));
            }
        }, 5000);
    });
}



/**
 * Handle incoming WebSocket messages
 */
async function handleWebSocketMessage(event) {
    if (event.data instanceof Blob) {
        // Binary audio data (TTS response)
        const arrayBuffer = await event.data.arrayBuffer();
        await playAudioResponse(arrayBuffer);
    } else {
        // Text/JSON message
        try {
            const message = JSON.parse(event.data);
            handleControlMessage(message);
        } catch (e) {
            log(`Invalid message: ${e}`, 'error');
        }
    }
}

/**
 * Handle control messages from server
 */
function handleControlMessage(message) {
    switch (message.type) {
        case 'auth_ok':
            log('Authentication successful', 'success');
            break;
        case 'auth_failed':
            log('Authentication failed', 'error');
            deactivate();
            break;
        case 'pong':
            // Keep-alive response
            break;
            if (message.rate) {
                STATE.currentTtsRate = message.rate;
                log(`TTS Sample Rate set to ${message.rate}Hz`, 'info');
            }
            break;
        case 'status':
            updateStatus('wyoming-status', 
                message.wyoming_connected ? 'connected' : 'disconnected',
                message.wyoming_connected ? 'Connected' : 'Disconnected'
            );
            // Handle Config if present (Overlay URL)
            const targetUrl = CONFIG.overlayUrl || (message.config && message.config.overlay_url);
            if (targetUrl && elements.iframe) {
                const currentSrc = elements.iframe.getAttribute('src');
                if (elements.iframe.src !== targetUrl && elements.iframe.src === 'about:blank') {
                    elements.iframe.src = targetUrl;
                    log(`Loaded overlay URL: ${targetUrl}`, 'info');
                }
            }
            break;
        case 'config_update':
             if (message.wake_word) {
                 log(`Server updated wake word to: ${message.wake_word}`, 'info');
                 CONFIG.wakeWord = message.wake_word;
                 if (elements.wakeWordSelect) elements.wakeWordSelect.value = message.wake_word;
                 if (STATE.isActive) loadWakeWordModel().catch(console.error);
             }
             break;
        case 'voice_event':
             handleVoiceEvent(message);
             break;
    }
}

/**
 * Handle voice assistant events (STT/TTS text)
 */
function handleVoiceEvent(message) {
    const eventType = message.event_type;
    const data = message.data || {};
    
    if (eventType === 3) { // STT_START
        showBubble("Listening...");
    } else if (eventType === 4) { // STT_END
        if (data.text) showBubble(`"${data.text}"`);
    } else if (eventType === 7) { // TTS_START
        if (data.text) showBubble(data.text);
    } else if (eventType === 2) { // RUN_END
        setTimeout(() => hideBubble(), 5000);
    }
}

function showBubble(text) {
    if (elements.bubbleText) {
        elements.bubbleText.textContent = text;
        if (elements.textBubble) elements.textBubble.classList.remove('hidden');
    }
}

function hideBubble() {
    if (elements.textBubble) elements.textBubble.classList.add('hidden');
}

/**
 * Request microphone access
 */
async function requestMicrophone() {
    try {
        log('Requesting microphone access...', 'info');
        STATE.mediaStream = await navigator.mediaDevices.getUserMedia({
            audio: {
                sampleRate: CONFIG.sampleRate,
                channelCount: CONFIG.channels,
                echoCancellation: true,
                noiseSuppression: true,
                autoGainControl: true
            }
        });
        updateStatus('mic-status', 'active', 'Active');
        log('Microphone access granted', 'success');
        
        const source = STATE.audioContext.createMediaStreamSource(STATE.mediaStream);
        await setupAudioProcessing(source);
        
    } catch (error) {
        throw new Error(`Microphone access denied: ${error.message}`);
    }
}

/**
 * Setup audio processing for wake word detection
 */
async function setupAudioProcessing(source) {
    try {
        await STATE.audioContext.audioWorklet.addModule('wake-word-processor.js');
        const workletNode = new AudioWorkletNode(STATE.audioContext, 'wake-word-processor');
        
        workletNode.port.onmessage = async (event) => {
            const float32Data = event.data;
            if (!STATE.isListening) await runWakeWordInference(float32Data);
            
            if (STATE.isListening && STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
                const int16Data = new Int16Array(float32Data.length);
                for (let i = 0; i < float32Data.length; i++) {
                    const s = Math.max(-1, Math.min(1, float32Data[i]));
                    int16Data[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
                }
                STATE.ws.send(int16Data.buffer);
            }
        };
        
        source.connect(workletNode);
        workletNode.connect(STATE.audioContext.destination);
        STATE.audioWorkletNode = workletNode;
        log('Audio processing configured (AudioWorklet)', 'info');
    } catch (e) {
        log(`Failed to setup AudioWorklet: ${e.message}`, 'error');
        throw e;
    }
}

/**
 * Run ONNX inference on audio chunk
 */
async function runWakeWordInference(float32Data) {
    if (!STATE.onnxSessions.mel || !STATE.onnxSessions.embedding || !STATE.onnxSessions.wakeWord) return;
    
    try {
        // --- 1. Melspectrogram ---
        // Input: Audio chunk [1, 1280]
        const melInputName = STATE.onnxSessions.mel.inputNames[0];
        const audioTensor = new ort.Tensor('float32', Float32Array.from(float32Data), [1, float32Data.length]);
        
        const melResults = await STATE.onnxSessions.mel.run({ [melInputName]: audioTensor });
        let melOutput = melResults[STATE.onnxSessions.mel.outputNames[0]].data;

        // Normalization (critical step from voice-satellite-card)
        for (let j = 0; j < melOutput.length; j++) {
            melOutput[j] = (melOutput[j] / 10.0) + 2.0;
        }

        // Split 160 features into 5 frames of 32
        for (let j = 0; j < 5; j++) {
            const frame = melOutput.subarray(j * 32, (j + 1) * 32);
            STATE.buffers.mel.push(new Float32Array(frame));
        }

        // Process while we have enough frames (sliding window)
        while (STATE.buffers.mel.length >= 76) {
             // Flatten Mel Buffer: [76, 32] -> [1, 76, 32, 1]
             const flatMel = new Float32Array(76 * 32);
             for (let i = 0; i < 76; i++) {
                 flatMel.set(STATE.buffers.mel[i], i * 32);
             }
             
             // --- 2. Embedding ---
             const embInputName = STATE.onnxSessions.embedding.inputNames[0];
             const melTensor = new ort.Tensor('float32', flatMel, [1, 76, 32, 1]);
             
             const embResults = await STATE.onnxSessions.embedding.run({ [embInputName]: melTensor });
             const embOutput = embResults[STATE.onnxSessions.embedding.outputNames[0]].data;
             
             // --- 3. Accumulate Embeddings ---
             STATE.buffers.emb.shift();
             STATE.buffers.emb.push(new Float32Array(embOutput));
             
             // Flatten Embedding: [16, 96]
             const flatEmb = new Float32Array(16 * 96);
             for (let i = 0; i < 16; i++) {
                 flatEmb.set(STATE.buffers.emb[i], i * 96);
             }
             
             // --- 4. Wake Word ---
             const item = STATE.onnxSessions.wakeWord; 
             const wwInputName = item.inputNames[0];
             const embTensor = new ort.Tensor('float32', flatEmb, [1, 16, 96]);
             
             const wwResults = await item.run({ [wwInputName]: embTensor });
             const probability = wwResults[item.outputNames[0]].data[0];
             
             // DEBUG: Log probability occasionally
             if (Math.random() < 0.1) {
                 console.log(`[DEBUG] Wake word probability: ${probability.toFixed(4)}`);
             }

             if (probability > 0.5) {
                  log(`Wake word detected! (${(probability * 100).toFixed(1)}%)`, 'success');
                  triggerWakeWord();
             }
             
             // Stride: Remove 8 frames from Mel buffer logic
             STATE.buffers.mel.splice(0, 8);
        }

    } catch (e) {
        if (!STATE.lastError || STATE.lastError !== e.message) {
            log(`Inference error: ${e.message}`, 'error');
            console.error(e);
            STATE.lastError = e.message;
        }
    }
}

function triggerWakeWord() {
    if (!STATE.isListening) {
        STATE.isListening = true;
        updateUI();
        
        // Notify server
        if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
            STATE.ws.send(JSON.stringify({ type: 'wake_detected' }));
        }
        
        // Stop listening after 15 seconds (Safety timeout)
        STATE.silenceTimer = setTimeout(() => {
            if (STATE.isListening) {
                STATE.isListening = false;
                updateUI();
                log('Listening timeout', 'info');
                
                // Reset buffers to avoid state pollution from the gap
                STATE.buffers.mel = [];
                STATE.buffers.emb = new Array(16).fill(0).map(() => new Float32Array(96).fill(0));
            }
        }, 8000);
    }
}

/**
 * Load wake word model (placeholder)
 */
/**
 * Load wake word models
 */
async function loadWakeWordModel() {
    try {
        log('Loading ONNX models...', 'info');
        
        const modelPath = 'models';
        const wakeWordId = CONFIG.wakeWord;
        
        // Load Melspectrogram model
        log('Loading melspectrogram model...', 'info');
        STATE.onnxSessions.mel = await ort.InferenceSession.create(`${modelPath}/melspectrogram.onnx`, { executionProviders: ['wasm'] });
        
        // Load Embedding model
        log('Loading embedding model...', 'info');
        STATE.onnxSessions.embedding = await ort.InferenceSession.create(`${modelPath}/embedding_model.onnx`, { executionProviders: ['wasm'] });
        
        // Load Wake Word model
        log(`Loading wake word model: ${wakeWordId}...`, 'info');
        STATE.onnxSessions.wakeWord = await ort.InferenceSession.create(`${modelPath}/${wakeWordId}.onnx`, { executionProviders: ['wasm'] });
        
        // Reset buffers
        STATE.buffers.mel = [];
        // Initialize embedding buffer with zero-filled arrays to match input shape [96]
        STATE.buffers.emb = new Array(16).fill(0).map(() => new Float32Array(96).fill(0));
        STATE.lastError = null;

        log(`Models loaded successfully`, 'success');
        
    } catch (error) {
        log(`Failed to load models: ${error.message}`, 'error');
        throw error;
    }
}

/**
 * Simulate wake word detection (for testing)
 */


/**
 * Play audio response from server
 */
/**
 * Play audio response from server (Raw PCM)
 */
async function playAudioResponse(arrayBuffer) {
    if (!STATE.audioContext) {
        if (STATE.isActive) {
             console.warn('AudioContext lost but state is active. Re-initializing...');
             await initAudioContext();
        } else {
             // Ignore audio if not active
             return;
        }
    }

    try {
        // Detect and skip WAV header (RIFF) to avoid static burst
        // RIFF = 0x52 0x49 0x46 0x46
        if (arrayBuffer.byteLength > 44) {
            const headerView = new DataView(arrayBuffer);
            if (headerView.getUint32(0, false) === 0x52494646) {
                log('Detected WAV header in stream. Skipping 44 bytes.', 'warning');
                arrayBuffer = arrayBuffer.slice(44);
            }
        }

        // Assume 16-bit Mono PCM, 16000Hz (Wyoming standard for Rhasspy)
        // If TTS is 22050Hz, we might need to adjust or read metadata
        const int16Data = new Int16Array(arrayBuffer);
        const float32Data = new Float32Array(int16Data.length);
        
        // Convert Int16 to Float32
        for (let i = 0; i < int16Data.length; i++) {
            float32Data[i] = int16Data[i] / 32768.0;
        }
        
        // Create AudioBuffer
        const rate = STATE.currentTtsRate || CONFIG.ttsSampleRate || 22050; // Use detected rate or fallback
        const buffer = STATE.audioContext.createBuffer(1, float32Data.length, rate);
        buffer.getChannelData(0).set(float32Data);
        
        // Schedule playback
        const source = STATE.audioContext.createBufferSource();
        source.buffer = buffer;
        source.connect(STATE.audioContext.destination);
        
        // Ensure continuous playback
        const currentTime = STATE.audioContext.currentTime;
        if (!STATE.nextAudioTime || STATE.nextAudioTime < currentTime) {
            STATE.nextAudioTime = currentTime;
        }
        
        source.start(STATE.nextAudioTime);
        STATE.nextAudioTime += buffer.duration;
        
        // log('Playing TTS chunk', 'info'); // Too noisy
    } catch (error) {
        log(`Failed to play audio: ${error.message}`, 'error');
    }
}

/**
 * Update UI based on current state
 */
function updateUI() {
    if (STATE.isListening) {
        if (elements.micVisualizer) {
            elements.micVisualizer.classList.remove('active');
            elements.micVisualizer.classList.add('listening');
        }
        if (elements.stateText) {
            elements.stateText.textContent = 'Listening...';
            elements.stateText.className = 'state-text listening';
        }
        if (elements.activateFab) {
            elements.activateFab.classList.add('listening');
        }
        if (elements.fabVisualizer) elements.fabVisualizer.classList.remove('hidden');
        
    } else if (STATE.isActive) {
        if (elements.micVisualizer) {
            elements.micVisualizer.classList.add('active');
            elements.micVisualizer.classList.remove('listening');
        }
        if (elements.stateText) {
            elements.stateText.textContent = 'Ready (Press SPACE)';
            elements.stateText.className = 'state-text active';
        }
        if (elements.activateFab) {
            elements.activateFab.classList.remove('listening');
            elements.activateFab.classList.add('active');
        }
        if (elements.fabVisualizer) elements.fabVisualizer.classList.add('hidden');
        
    } else {
        if (elements.micVisualizer) {
            elements.micVisualizer.classList.remove('active', 'listening');
        }
        if (elements.stateText) {
            elements.stateText.textContent = 'Click to activate';
            elements.stateText.className = 'state-text';
        }
        if (elements.activateFab) {
            elements.activateFab.classList.remove('active', 'listening');
        }
        if (elements.fabVisualizer) elements.fabVisualizer.classList.add('hidden');
    }
}

/**
 * Update status badge
 */
function updateStatus(elementId, status, text) {
    const element = document.getElementById(elementId);
    if (element) {
        element.className = `status-badge ${status}`;
        element.textContent = text;
    }
    
    // Update FAB connection dot if it exists
    if (elements.connectionStatus && elementId === 'ws-status') {
        elements.connectionStatus.className = `status-dot ${status}`;
    }
}

/**
 * Toggle settings panel
 */
function toggleSettings() {
    elements.settingsPanel.classList.toggle('hidden');
}

/**
 * Save settings
 */
function saveSettings() {
    CONFIG.wsUrl = elements.wsUrlInput.value;
    CONFIG.wakeWord = elements.wakeWordSelect.value;
    CONFIG.wsUrl = elements.wsUrlInput.value;
    CONFIG.wakeWord = elements.wakeWordSelect.value;
    CONFIG.authToken = elements.authTokenInput.value;
    if (elements.overlayUrlInput) CONFIG.overlayUrl = elements.overlayUrlInput.value;
    
    localStorage.setItem('wsUrl', CONFIG.wsUrl);
    localStorage.setItem('wakeWord', CONFIG.wakeWord);
    localStorage.setItem('authToken', CONFIG.authToken);
    if (elements.overlayUrlInput) localStorage.setItem('overlayUrl', CONFIG.overlayUrl);
    
    // Apply Overlay URL immediately if changed
    if (CONFIG.overlayUrl && elements.iframe && elements.iframe.src !== CONFIG.overlayUrl) {
        elements.iframe.src = CONFIG.overlayUrl;
    }
    
    // Reload models if active
    if (STATE.isActive) {
        loadWakeWordModel().catch(console.error);
    }
    
    log('Settings saved', 'success');
    toggleSettings();
}

/**
 * Log message to debug panel
 */
function log(message, type = 'info') {
    const time = new Date().toLocaleTimeString();
    const entry = document.createElement('div');
    entry.className = 'log-entry';
    entry.innerHTML = `<span class="log-time">${time}</span><span class="log-${type}">${message}</span>`;
    elements.debugLog.appendChild(entry);
    elements.debugLog.scrollTop = elements.debugLog.scrollHeight;
    
    console.log(`[${type.toUpperCase()}] ${message}`);
}

/**
 * Clear debug log
 */
function clearLog() {
    elements.debugLog.innerHTML = '';
    log('Log cleared', 'info');
}

/**
 * Send periodic keep-alive ping
 */
function startKeepAlive() {
    setInterval(() => {
        if (STATE.ws && STATE.ws.readyState === WebSocket.OPEN) {
            STATE.ws.send(JSON.stringify({ type: 'ping' }));
        }
    }, 30000); // Every 30 seconds
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    init();
    startKeepAlive();
});

// Handle page unload
window.addEventListener('beforeunload', () => {
    deactivate();
});
