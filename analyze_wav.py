import wave
import struct
import math

filename = "server/debug_20260103_144933.wav"

try:
    with wave.open(filename, 'rb') as wf:
        params = wf.getparams()
        print(f"Channels: {params.nchannels}")
        print(f"Sample Width: {params.sampwidth} bytes")
        print(f"Frame Rate: {params.framerate} Hz")
        print(f"Frames: {params.nframes}")
        duration = params.nframes / params.framerate
        print(f"Duration: {duration:.2f} seconds")
        
        # Read all frames
        data = wf.readframes(params.nframes)
        total_samples = len(data) // params.sampwidth
        
        # Calculate RMS and Peak
        sum_squares = 0
        max_val = 0
        
        # Assume 16-bit little endian (as set in server)
        fmt = "<" + ("h" * total_samples)
        samples = struct.unpack(fmt, data)
        
        for sample in samples:
            val = abs(sample)
            if val > max_val:
                max_val = val
            sum_squares += sample * sample
            
        rms = math.sqrt(sum_squares / total_samples)
        
        print(f"RMS Amplitude: {int(rms)}")
        print(f"Peak Amplitude: {max_val}")
        print(f"Max Possible Amplitude: 32768")
        
        if rms < 100:
            print("Status: SILENCE DETECTED")
        elif rms < 500:
            print("Status: LOW VOLUME / NOISE")
        else:
            print("Status: ACTIVE AUDIO")

except Exception as e:
    print(f"Error analyzing wav: {e}")

