
import asyncio
import logging
import socket
from typing import Callable, Optional

import aioesphomeapi.api_pb2 as pb2
from .frame_helper import APIFrameHelper

_LOGGER = logging.getLogger(__name__)

class ESPHomeServerProtocol(asyncio.Protocol):
    """Asyncio Protocol for ESPHome Native API Server."""

    def __init__(self, on_connect: Callable, on_message: Callable):
        self.transport = None
        self.on_connect = on_connect
        self.on_message = on_message
        self._frame_helper = APIFrameHelper()
        self._authenticated = False

    def connection_made(self, transport):
        peername = transport.get_extra_info('peername')
        _LOGGER.info('Connection from %s', peername)
        self.transport = transport
        if self.on_connect:
            self.on_connect(self)

    def connection_lost(self, exc):
        _LOGGER.info("Connection lost: %s", exc)


    def data_received(self, data):
        self._frame_helper.feed_data(data)
        while True:
            packet = self._frame_helper.read_packet()
            if packet is None:
                break
            msg_type, msg_data = packet
            self._handle_packet(msg_type, msg_data)

    def _handle_packet(self, msg_type: int, data: bytes):
        """Dispatch packet to handler."""
        try:
            if msg_type == 1:  # HelloRequest
                req = pb2.HelloRequest()
                req.ParseFromString(data)
                self._handle_hello(req)

            # ConnectRequest/AuthenticationRequest is type 3
            # DisconnectRequest is type 5
            # PingRequest is type 7
            
            elif msg_type == 3: # ConnectRequest (AuthenticationRequest)
                 req = pb2.AuthenticationRequest()
                 req.ParseFromString(data)
                 self._handle_connect(req)
            elif msg_type == 5: # DisconnectRequest
                 self._handle_disconnect()
            elif msg_type == 7: # PingRequest
                 self._send_message(pb2.PingResponse(), 8)
            elif msg_type == 9: # DeviceInfoRequest
                 self.on_message(self, msg_type, data)
            elif msg_type == 11: # ListEntitiesRequest
                 self.on_message(self, msg_type, data)
            elif msg_type == 20: # SubscribeStatesRequest
                 self.on_message(self, msg_type, data)
            else:
                 self.on_message(self, msg_type, data)

        except Exception as e:
            _LOGGER.error("Error handling packet type %s: %s", msg_type, e, exc_info=True)

    def _handle_hello(self, req):
        _LOGGER.debug("Received HelloRequest: client=%s", req.client_info)
        resp = pb2.HelloResponse()
        resp.api_version_major = 2
        resp.api_version_minor = 10
        resp.server_info = "HybridSatellite"
        resp.name = "hybrid-satellite"
        self._send_message(resp, 2) 

    def _handle_connect(self, req):
         _LOGGER.info("Received ConnectRequest: pwd=%s", req.password)
         resp = pb2.AuthenticationResponse()
         resp.invalid_password = False 
         self._authenticated = True
         self._send_message(resp, 4) 

    def _handle_disconnect(self):
        _LOGGER.info("Received DisconnectRequest")
        resp = pb2.DisconnectResponse()
        self._send_message(resp, 6) 
        self.transport.close()

    def send_message(self, msg, msg_type: int):
        """Public method to send a message."""
        self._send_message(msg, msg_type)

    def _send_message(self, msg, msg_type: int):
        data = self._frame_helper.encode_frame(msg, msg_type)
        self.transport.write(data)
