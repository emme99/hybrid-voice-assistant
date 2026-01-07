"""
Wyoming protocol server for integration with Home Assistant.
Home Assistant connects to this server to receive audio and send TTS.
"""
import asyncio
import json
import logging
from typing import Optional, Dict, Any, Set

logger = logging.getLogger(__name__)


import wave
import datetime
import numpy as np
from scipy import signal

def resample_audio(audio_bytes: bytes, orig_rate: int = 22050, target_rate: int = 16000) -> bytes:
    """Resample audio bytes from orig_rate to target_rate using polyphase filtering."""
    try:
        if not audio_bytes:
            return b""
        
        # Convert bytes to numpy array (assume int16)
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)
        
        # Calculate resampling factors (up/down)
        # 16000/22050 ~ 320/441
        # We can implement a simple GCD reducer or just pass them raw, scipy handles it but efficient is better
        gcd = np.gcd(orig_rate, target_rate)
        up = int(target_rate // gcd)
        down = int(orig_rate // gcd)
        
        # Resample using polyphase filter (better for audio than FFT resample)
        # Cast to float32 for processing to avoid overflow during filtering
        audio_float = audio_array.astype(np.float32)
        resampled_float = signal.resample_poly(audio_float, up, down)
        
        # Clip to int16 range and convert back
        resampled_clipped = np.clip(resampled_float, -32768, 32767)
        return resampled_clipped.astype(np.int16).tobytes()
        
    except Exception as e:
        logger.error(f"Resampling failed: {e}")
        return audio_bytes

class WyomingServer:
    """
    Server for Wyoming protocol.
    Accepts connections from Home Assistant.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 10700, name: str = "hybrid-voice-satellite-v2"):
        """
        Initialize Wyoming server.
        
        Args:
            host: Host to bind to
            port: Port to bind to (default 10700)
            name: Satellite name to identify in HA
        """
        self.host = host
        self.port = port
        self.name = name
        self.server: Optional[asyncio.AbstractServer] = None
        self.ha_writers: Set[asyncio.StreamWriter] = set()
        self.client_tasks: Set[asyncio.Task] = set()
        self.debug_wav = None
        self.pending_tts_audio = bytearray()
        self.tts_sample_rate = 22050 # Default, will update from audio-start
    
    async def start(self):
        """Start the Wyoming TCP server."""
        self.server = await asyncio.start_server(
            self.handle_client, self.host, self.port
        )
        logger.info(f"Wyoming server listening on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop the server."""
        logger.debug("Stopping Wyoming server...")
        
        # 1. Cancel active tasks (Stop processing)
        logger.debug(f"Cancelling {len(self.client_tasks)} active tasks...")
        if self.client_tasks:
            for task in list(self.client_tasks):
                task.cancel()
            
            try:
                await asyncio.wait_for(asyncio.gather(*self.client_tasks, return_exceptions=True), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for tasks to cancel")
            self.client_tasks.clear()

        # 2. Close active connections (Stop I/O)
        logger.debug(f"Closing {len(self.ha_writers)} active connections...")
        for writer in list(self.ha_writers):
            writer.close()
            
        if self.ha_writers:
            tasks = [writer.wait_closed() for writer in self.ha_writers]
            try:
                await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for connections to close")
            self.ha_writers.clear()

        # 3. Stop listener (Stop new connections)
        if self.server:
            self.server.close()
            try:
                await asyncio.wait_for(self.server.wait_closed(), timeout=1.0)
            except asyncio.TimeoutError:
                logger.warning("Timeout waiting for server to close")
        
        logger.info("Wyoming server stopped")
        
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming connection from Home Assistant."""
        task = asyncio.current_task()
        self.client_tasks.add(task)
        
        addr = writer.get_extra_info('peername')
        logger.info(f"Home Assistant connected from {addr}")
        self.ha_writers.add(writer)
        
        try:
            # Send handshake immediately upon connection
            handshake = {
                'type': 'satellite',
                'name': self.name,
                'area': None,
                'description': 'Hybrid Voice Satellite',
                'attribution': {
                    'name': 'Hybrid Voice Satellite',
                    'url': 'https://github.com/emme/hybrid-voice-satellite'
                },
                'installed': True,
                'version': '0.1.0',
                'capabilities': ['wake_word', 'audio_input', 'audio_output'],
                'snd_format': {
                    'rate': 22050,
                    'width': 2,
                    'channels': 1,
                }
            }
            logger.debug(f"Sending handshake to {addr}: {handshake}")
            await self.send_json(writer, handshake)
            
            # Message loop
            pending_data = None
            while True:
                try:
                    line = await reader.readline()
                except ConnectionResetError:
                    break
                    
                if not line:
                    logger.info(f"Connection closed by {addr} (EOF)")
                    break
                
                try:
                    # Use ignore to prevent crash on binary data, but likely means we are desynced
                    decoded_line = line.decode('utf-8', errors='ignore').strip()
                    if not decoded_line:
                        continue
                        
                    decoder = json.JSONDecoder(strict=False)
                    pos = 0
                    while pos < len(decoded_line):
                        # Skip whitespace
                        while pos < len(decoded_line) and decoded_line[pos].isspace():
                            pos += 1
                        if pos >= len(decoded_line):
                            break
                        
                        # Verify we are at the start of a JSON object
                        if decoded_line[pos] != '{':
                            # logger.warning(f"Invalid JSON start char '{decoded_line[pos]}' at pos {pos}. Scanning for next '{{'...")
                            next_brace = decoded_line.find('{', pos)
                            if next_brace == -1:
                                logger.debug(f"No JSON object found in remaining text: {repr(decoded_line[pos:])}")
                                break
                            pos = next_brace
                            
                        # Parse JSON object
                        try:
                            message, idx = decoder.raw_decode(decoded_line, pos)
                            pos = idx
                        except json.JSONDecodeError:
                            # The '{' we found might be part of binary garbage or incomplete.
                            pos += 1
                            continue
                        
                        if not isinstance(message, dict):
                            logger.warning(f"Ignored non-dict message: {message}")
                            continue

                        # logger.debug(f"Parsed message: {message.get('type')}")
                        
                        # 1. Check for data (JSON metadata)
                        data_length = message.get('data_length')
                        if data_length:
                             try:
                                 data_bytes = await reader.readexactly(data_length)
                                 data_obj = json.loads(data_bytes)
                                 # Merge into message['data']
                                 if 'data' not in message:
                                     message['data'] = {}
                                 if isinstance(data_obj, dict):
                                     message['data'].update(data_obj)
                             except asyncio.IncompleteReadError:
                                 logger.error(f"Incomplete data read from {addr}")
                                 return # Close connection
                             except json.JSONDecodeError:
                                 logger.error(f"Invalid JSON data block from {addr}")
                                 return # Close connection

                        # 2. Check for binary payload (Audio)
                        payload = None
                        payload_length = message.get('payload_length')
                        if payload_length:
                            try:
                                payload = await reader.readexactly(payload_length)
                            except asyncio.IncompleteReadError:
                                logger.error(f"Incomplete payload read from {addr}")
                                return # Close connection
                        
                        await self.handle_message(message, payload, writer)

                except UnicodeDecodeError:
                    logger.error(f"Invalid UTF-8 received from {addr}")
                    return # Close connection
                except Exception as e:
                     logger.error(f"Error processing line from {addr}: {e}", exc_info=True)
                     return # Close connection to be safe
                    
        except asyncio.CancelledError:
            # Handle task cancellation gracefully
            raise
        except ConnectionResetError:
            logger.info(f"Connection reset by {addr}")
        except Exception as e:
            logger.error(f"Error handling HA client {addr}: {e}", exc_info=True)

        finally:
            logger.info(f"Home Assistant disconnected from {addr}")
            self.ha_writers.discard(writer)
            self.client_tasks.discard(task)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    async def handle_message(self, message: Dict[str, Any], payload: Optional[bytes], writer: asyncio.StreamWriter):
        """Process incoming message from Home Assistant."""
        msg_type = message.get('type')
        if not msg_type:
             return
             
        logger.info(f"Received from HA: {msg_type} (payload: {len(payload) if payload else 0} bytes)")
        
        if msg_type == 'ping':
            await self.send_json(writer, {'type': 'pong'})

        elif msg_type == 'describe':
            # Resend handshake/info in response to describe
            handshake = {
                'type': 'info',
                'data': {
                    'nickname': self.name,
                    'version': '0.1.0',
                    'attribution': {
                        'name': 'Hybrid Voice Satellite',
                        'url': 'https://github.com/emme/hybrid-voice-satellite'
                    },
                    'installed': True,
                    'satellite': {
                        'name': self.name,
                        'area': 'Office',
                        'description': 'Hybrid Voice Satellite',
                        'attribution': {
                            'name': 'Hybrid Voice Satellite',
                            'url': 'https://github.com/emme/hybrid-voice-satellite'
                        },
                        'installed': True,
                        'version': '0.1.0',
                        'components': [],
                        'capabilities': ['wake_word', 'audio_input', 'audio_output'],
                        'snd_format': {
                            'rate': 22050,
                            'width': 2,
                            'channels': 1,
                        }
                    }
                }
            }
            logger.info(f"Sending info response: {handshake}")
            await self.send_json(writer, handshake)
            
        elif msg_type == 'audio-start':
            # Start of TTS stream
            data = message.get('data', {})
            rate = data.get('rate', 22050)
            width = data.get('width', 2)
            channels = data.get('channels', 1)
            
            logger.info(f"TTS Stream started. Format: {rate}Hz, {width} bytes/sample, {channels} ch")
            
            # Notify handler (e.g. WebSocket server) to prepare client
            if hasattr(self, 'on_tts_start'):
                await self.on_tts_start(rate)

        elif msg_type in ('audio', 'audio-chunk'):
            # TTS Audio chunk received
            audio_bytes = payload
            if not audio_bytes:
                data_hex = message.get('data')
                if data_hex:
                    audio_bytes = bytes.fromhex(data_hex)
            
            if audio_bytes:
                if hasattr(self, 'on_tts_audio'):
                    # Pass-through: Send raw bytes to client immediately
                    await self.on_tts_audio(audio_bytes)

        elif msg_type == 'audio-stop':
            # End of TTS stream
            logger.info("TTS Stream ended.")
            
            if hasattr(self, 'on_tts_stop'):
                await self.on_tts_stop()
                
            # Signal playback finished to HA (Required for media player status)
            await self.send_json(writer, {'type': 'played'})
    
        elif msg_type == 'run_pipeline':
            # HA requesting pipeline run (might not be needed if we drive it)
            pass

    async def send_audio(self, audio_data: bytes):
        """Broadcast audio chunk to all connected HA instances."""
        if not self.ha_writers:
            return
        
        message = {
            'type': 'audio-chunk',
            'data': {
                'rate': 16000,
                'width': 2,
                'channels': 1,
            },
            'payload_length': len(audio_data),
        }
        
        # Broadcast to all
        for writer in list(self.ha_writers):
            try:
                # Send JSON headers
                await self.send_json(writer, message)
                # Send binary payload
                writer.write(audio_data)
                await writer.drain()
            except Exception as e:
                logger.error(f"Failed to send audio to HA: {e}")
                self.ha_writers.discard(writer)

    async def send_wake_word_detected(self):
        """Notify HA to start a pipeline."""
        
        # 1. Start Pipeline
        # We start the pipeline at the 'stt' stage since we already did wake word
        pipeline_message = {
            'type': 'run-pipeline',
            'data': {
                'start_stage': 'asr',
                'end_stage': 'tts',
                'restart_on_end': False,
            }
        }
        
        for writer in list(self.ha_writers):
            try:
                await self.send_json(writer, pipeline_message)
            except Exception:
                pass

    async def send_json(self, writer: asyncio.StreamWriter, message: Dict[str, Any]):
        """Send JSON message to specific writer."""
        # logger.debug(f"Sending to HA: {message}")
        logger.info(f"Sending to HA: {message['type']} ({message.get('payload_length', 0)} bytes payload)")
        data = json.dumps(message).encode() + b'\n'
        writer.write(data)
        await writer.drain()

    # Callback hook
    async def on_tts_audio(self, audio_data: bytes):
        """Override to handle TTS audio."""
        pass
