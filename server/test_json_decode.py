import json

def test_decode():
    # The string from the logs (simulated)
    # {"rate": 22050, "width": 2, "channels": 1, "timestamp": 2239}{"type": "audio-chunk", "version": "1.7.2", "data_length": 61, "payload_length": 1778}
    s = '{"rate": 22050, "width": 2, "channels": 1, "timestamp": 2239}{"type": "audio-chunk", "version": "1.7.2", "data_length": 61, "payload_length": 1778}'
    
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(s):
        print(f"Decoding from pos {pos}")
        try:
            obj, idx = decoder.raw_decode(s, pos)
            print(f"Success! Object: {obj}")
            print(f"New index: {idx}")
            pos = idx
        except json.JSONDecodeError as e:
            print(f"Failed to decode: {e}")
            break

if __name__ == "__main__":
    test_decode()
