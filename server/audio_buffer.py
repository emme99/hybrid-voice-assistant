"""
Audio buffer module for managing audio chunks with async queue.
"""
import asyncio
from collections import deque
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class AudioBuffer:
    """
    Manages audio buffering with async queue for non-blocking I/O.
    Handles chunking audio data for optimal streaming performance.
    """
    
    def __init__(self, sample_rate: int = 16000, chunk_duration_ms: int = 30):
        """
        Initialize audio buffer.
        
        Args:
            sample_rate: Audio sample rate in Hz (default 16000)
            chunk_duration_ms: Chunk duration in milliseconds (default 30)
        """
        self.sample_rate = sample_rate
        self.chunk_duration_ms = chunk_duration_ms
        # Calculate chunk size in bytes (16-bit audio = 2 bytes per sample)
        self.chunk_size = int(sample_rate * chunk_duration_ms / 1000) * 2
        self.buffer = deque()
        self.queue = asyncio.Queue()
        logger.info(
            f"AudioBuffer initialized: {sample_rate}Hz, "
            f"{chunk_duration_ms}ms chunks, {self.chunk_size} bytes per chunk"
        )
    
    def add(self, audio_data: bytes):
        """
        Add audio chunk to buffer and create properly sized chunks.
        
        Args:
            audio_data: Raw audio bytes (16-bit PCM)
        """
        self.buffer.extend(audio_data)
        
        # Create chunks of appropriate size
        while len(self.buffer) >= self.chunk_size:
            chunk = bytes([self.buffer.popleft() for _ in range(self.chunk_size)])
            self.queue.put_nowait(chunk)
    
    async def get_chunk(self) -> bytes:
        """
        Get next audio chunk from queue (blocks if empty).
        
        Returns:
            Audio chunk as bytes
        """
        return await self.queue.get()
    
    def clear(self):
        """Clear all buffered audio data."""
        self.buffer.clear()
        # Clear queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.debug("Audio buffer cleared")
    
    @property
    def buffered_bytes(self) -> int:
        """Get number of bytes currently buffered."""
        return len(self.buffer)
    
    @property
    def queued_chunks(self) -> int:
        """Get number of chunks in queue."""
        return self.queue.qsize()
