
import struct
import logging
from typing import Optional, Tuple
from google.protobuf import message

_LOGGER = logging.getLogger(__name__)

class APIFrameHelper:
    """Helper class to handle ESPHome API frames."""

    def __init__(self):
        self._buffer = b""

    @staticmethod
    def encode_frame(msg: message.Message, msg_type: int) -> bytes:
        """Encode a protobuf message into an API frame."""
        data = msg.SerializeToString()
        # Framing: 0x00 (1 byte) + Length (varuint) + Type (varuint) + Data
        # Simplified: Length and Type are varints.
        # But standard ESPHome API uses:
        # Preamble (0x00) - 1 byte
        # Length - varint
        # Type - varint
        # Data
        
        # We need a varint encoder.
        encoded_length = APIFrameHelper._encode_varint(len(data))
        encoded_type = APIFrameHelper._encode_varint(msg_type)
        
        return b'\x00' + encoded_length + encoded_type + data

    @staticmethod
    def _encode_varint(value: int) -> bytes:
        """Encode an integer as a varint."""
        if value < 0:
             raise ValueError("Varint cannot be negative")
        
        bytes_list = []
        while value > 0x7f:
            bytes_list.append((value & 0x7f) | 0x80)
            value >>= 7
        bytes_list.append(value)
        return bytes(bytes_list)

    @staticmethod
    def _decode_varint(buffer: bytes, offset: int) -> Tuple[int, int]:
        """Decode a varint from buffer at offset. Returns (value, new_offset)."""
        value = 0
        shift = 0
        while True:
            if offset >= len(buffer):
                raise IndexError("Buffer too short for varint")
            byte = buffer[offset]
            offset += 1
            value |= (byte & 0x7f) << shift
            if not (byte & 0x80):
                break
            shift += 7
        return value, offset

    def feed_data(self, data: bytes) -> bytes:
        """Feed data into the buffer."""
        self._buffer += data
        
    def read_packet(self) -> Optional[Tuple[int, bytes]]:
        """
        Try to read a single packet from the buffer.
        Returns (type, data) if a full packet is found, else None.
        """
        if not self._buffer:
            return None
            
        # Check preamble
        if self._buffer[0] != 0:
            # Sync recovery: Look for next 0x00
            _LOGGER.warning("Invalid preamble 0x%02x, skipping", self._buffer[0])
            try:
                idx = self._buffer.index(b'\x00')
                self._buffer = self._buffer[idx:]
            except ValueError:
                self._buffer = b""
                return None

        # Need at least preamble (1) + length (1 min) + type (1 min)
        if len(self._buffer) < 3:
            return None

        try:
            offset = 1
            length, offset = self._decode_varint(self._buffer, offset)
            msg_type, offset = self._decode_varint(self._buffer, offset)
            
            total_size = offset + length
            if len(self._buffer) < total_size:
                return None
                
            data = self._buffer[offset:total_size]
            self._buffer = self._buffer[total_size:]
            
            return msg_type, data
            
        except IndexError:
            # Buffer incomplete for varint decoding
            return None
