class WakeWordProcessor extends AudioWorkletProcessor {
    constructor() {
        super();
        this._buffer = [];
        this._bufferSize = 1280; // Estimate for ~80ms chunks (16kHz)
        this._sampleRate = 16000;
    }

    process(inputs, outputs, parameters) {
        const input = inputs[0];
        if (input.length > 0) {
            const channelData = input[0];
            
            // Check actual sample rate
            // globalThis.sampleRate is available in AudioWorklet
            const currentSampleRate = sampleRate; 
            const targetSampleRate = 16000;
            
            if (currentSampleRate === targetSampleRate) {
                // Pass through
                for (let i = 0; i < channelData.length; i++) {
                    this._buffer.push(channelData[i]);
                }
            } else {
                // Linear Interpolation Downsampling
                // Handles non-integer ratios (e.g. 44100 -> 16000) and avoids aliasing jitter
                
                const ratio = currentSampleRate / targetSampleRate;
                
                // Initialize state if first run
                if (this._phase === undefined) {
                    this._phase = 0;
                    this._lastSample = 0;
                }
                
                let i = this._phase;
                const len = channelData.length;
                
                while (i < len) {
                    const idx = Math.floor(i);
                    const frac = i - idx;
                    
                    let s0, s1;
                    
                    if (idx === -1) {
                        // Interpolate between last chunk's end and this chunk's start
                        s0 = this._lastSample;
                        s1 = channelData[0];
                    } else if (idx < len - 1) {
                        // Interpolate within this chunk
                        s0 = channelData[idx];
                        s1 = channelData[idx + 1];
                    } else {
                        // We reached the end of the chunk without enough data for the next sample
                        // Break and carry over phase
                        break;
                    }
                    
                    // Linear interpolation formula: y = y0 + (y1-y0)*frac
                    const val = s0 + (s1 - s0) * frac;
                    this._buffer.push(val);
                    
                    i += ratio;
                }
                
                // Update state for next chunk
                // New phase matches the position relative to the start of the next chunk
                // Logic: We stopped at 'i'. The start of next chunk is at index 'len'.
                // So relative phase is i - len.
                this._phase = i - len;
                this._lastSample = channelData[len - 1]; // Save last sample for boundary interpolation
            }

            // Flush buffer when full
            if (this._buffer.length >= this._bufferSize) {
                this.port.postMessage(this._buffer);
                this._buffer = [];
            }
        }
        return true;
    }
}

registerProcessor('wake-word-processor', WakeWordProcessor);
