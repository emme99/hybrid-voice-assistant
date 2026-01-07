import asyncio
import json
from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.pipeline import RunPipeline, PipelineStage
from wyoming.info import Describe, Info

async def main():
    # 1. RunPipeline
    run_pipeline = RunPipeline(start_stage=PipelineStage.ASR, end_stage=PipelineStage.TTS, restart_on_end=False)
    print("RunPipeline JSON:")
    print(json.dumps(run_pipeline.event().to_dict()))
    print("-" * 20)

    # 2. AudioStart
    audio_start = AudioStart(rate=16000, width=2, channels=1)
    print("AudioStart JSON:")
    print(json.dumps(audio_start.event().to_dict()))
    print("-" * 20)

    # 3. AudioChunk
    chunk = AudioChunk(rate=16000, width=2, channels=1, data=b'\x00'*10)
    event = chunk.event()
    print("AudioChunk JSON (Header):")
    print(json.dumps(event.to_dict()))
    print(f"Payload Length: {len(event.payload)}")
    print("-" * 20)

    # 4. AudioStop
    audio_stop = AudioStop()
    print("AudioStop JSON:")
    print(json.dumps(audio_stop.event().to_dict()))
    print("-" * 20)

if __name__ == "__main__":
    asyncio.run(main())
