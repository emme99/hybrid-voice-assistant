
import logging
import asyncio
from typing import Optional, List

import aioesphomeapi.api_pb2 as pb2
from .api_server import ESPHomeServerProtocol

_LOGGER = logging.getLogger(__name__)

class ESPHomeProtocolHandler:
    """High-level handler for ESPHome Protocol."""

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.protocol: Optional[ESPHomeServerProtocol] = None
        self._connected = False
        self.websocket_server = None 

    def set_websocket_server(self, ws_server):
        self.websocket_server = ws_server

    def on_connect(self, protocol: ESPHomeServerProtocol):
        _LOGGER.info("ESPHome Client Connected")
        self.protocol = protocol
        self._connected = True

    def on_message(self, protocol: ESPHomeServerProtocol, msg_type: int, data: bytes):
        """Handle incoming messages from HA."""
        try:
            if msg_type == 9: # DeviceInfoRequest
                self._handle_device_info()
            elif msg_type == 11: # ListEntitiesRequest
                self._handle_list_entities()
            elif msg_type == 20: # SubscribeStatesRequest
                _LOGGER.info("Received SubscribeStatesRequest")
                self._handle_subscribe_states()
            elif msg_type == 52: # DELETE OR MOVE TO 90?
                 # HA sends 90? Unlikely, but let's keep it safe. 
                 # Actually, delete 52-55 block and add new ones.
                 pass

            # Correct IDs:
            elif msg_type == 89: # SubscribeVoiceAssistantRequest
                 req = pb2.SubscribeVoiceAssistantRequest()
                 req.ParseFromString(data)
                 _LOGGER.info("Received SubscribeVoiceAssistantRequest: sub=%s", req.subscribe)
            
            elif msg_type == 91: # VoiceAssistantResponse
                 resp = pb2.VoiceAssistantResponse()
                 resp.ParseFromString(data)
                 _LOGGER.info("Received VoiceAssistantResponse: port=%s, error=%s", resp.port, resp.error)
            
            elif msg_type == 92: # VoiceAssistantEventResponse
                 event = pb2.VoiceAssistantEventResponse()
                 event.ParseFromString(data)
                 _LOGGER.info("Received VoiceAssistantEvent: type=%s", event.event_type)
                 
                 event_data = {}
                 for item in event.data:
                     event_data[item.name] = item.value
                 
                 # Forward to websocket
                 if self.websocket_server:
                     asyncio.run_coroutine_threadsafe(
                         self.websocket_server.broadcast_message({
                             "type": "voice_event",
                             "event_type": event.event_type,
                             "data": event_data
                         }),
                         self.loop
                     )

            elif msg_type == 121: # VoiceAssistantConfigurationRequest
                 # No data in request
                 _LOGGER.info("Received VoiceAssistantConfigurationRequest")
                 self._handle_voice_assistant_configuration_request(None)

            elif msg_type == 123: # VoiceAssistantSetConfiguration
                 req = pb2.VoiceAssistantSetConfiguration()
                 req.ParseFromString(data)
                 self._handle_voice_assistant_set_configuration(req)

            elif msg_type == 65: # MediaPlayerCommandRequest
                 cmd = pb2.MediaPlayerCommandRequest()
                 cmd.ParseFromString(data)
                 _LOGGER.info("Received MediaPlayerCommandRequest: cmd=%s, url=%s, vol=%s", 
                              cmd.command, cmd.media_url if cmd.has_media_url else "None", 
                              cmd.volume if cmd.has_volume else "N/A")
                 
                 if cmd.has_media_url and cmd.media_url:
                     asyncio.create_task(self._play_media_url(cmd.media_url))

            elif msg_type == 106: # VoiceAssistantAudio (Incoming TTS)
                 audio = pb2.VoiceAssistantAudio()
                 audio.ParseFromString(data)
                 # Forward audio to websocket clients (browsers)
                 if self.websocket_server:
                     # Create task to avoid blocking this loop
                     asyncio.run_coroutine_threadsafe(
                         self.websocket_server.broadcast_audio(audio.data),
                         self.loop
                     )
            
            else:
                _LOGGER.debug("Unhandled message type: %s", msg_type)
        except Exception as e:
            _LOGGER.error("Error handling message %s: %s", msg_type, e)

    def _send(self, msg, msg_type: int):
        if self.protocol:
            self.protocol.send_message(msg, msg_type)

    def _map_ww_to_client(self, ha_ww):
        """Map HA wake word ID to Client wake word ID."""
        if ha_ww == "alexa": return "alexa_v0.1"
        if ha_ww == "okay_nabu": return "okay_nabu_v0.1"
        return ha_ww # Fallback

    def _map_ww_to_ha(self, client_ww):
        """Map Client wake word ID to HA wake word ID."""
        if client_ww == "alexa_v0.1": return "alexa"
        if client_ww == "okay_nabu_v0.1": return "okay_nabu"
        return client_ww # Fallback

    def initiate_pipeline(self, wake_word: str = None):
        """Tell HA to start the pipeline."""
        ha_ww = self._map_ww_to_ha(wake_word)
        _LOGGER.info("Initiating pipeline with wake word: %s (HA ID: %s)", wake_word, ha_ww)
        req = pb2.VoiceAssistantRequest()
        req.start = True
        if wake_word:
             req.wake_word_phrase = ha_ww
        
        # Flags: USE_VAD(1) | USE_WAKE_WORD(2)
        # We handle Wake Word locally, so we don't want HA to try and use its WW engine.
        # Sending flag 0 (or just not setting bit 2) should tell HA to skip WW stage.
        req.flags = 0 
        # if wake_word:
        #    req.flags |= 2

        # Audio settings
        settings = pb2.VoiceAssistantAudioSettings()
        settings.noise_suppression_level = 0
        settings.auto_gain = 0
        settings.volume_multiplier = 1.0
        req.audio_settings.CopyFrom(settings)

        self._send(req, 90) # ID 90

    def _handle_device_info(self):
        resp = pb2.DeviceInfoResponse()
        resp.mac_address = "02:00:00:00:00:01" 
        resp.name = "Hybrid Voice Assistant"
        resp.model = "Generic"
        resp.manufacturer = "ESPHome"
        resp.project_name = "hybrid.voice_assistant"
        resp.project_version = "1.0.0"
        resp.esphome_version = "2024.10.2"
        # Flags: VOICE_ASSISTANT(1) | SPEAKER(2) | API_AUDIO(4) | TIMERS(8) | ANNOUNCE(16) | START_CONVERSATION(32)
        resp.voice_assistant_feature_flags = 1 | 2 | 4 | 8 | 16 | 32
        self._send(resp, 10) 

    def _handle_list_entities(self):
        # Add Media Player
        mp = pb2.ListEntitiesMediaPlayerResponse()
        mp.object_id = "hybrid_voice_assistant_speaker"
        mp.key = 1
        mp.name = "Hybrid Voice Assistant Speaker"
        mp.supports_pause = True
        # Feature flags: PAUSE | VOLUME_SET | VOLUME_MUTE | PLAY_MEDIA | BROWSE_MEDIA
        mp.feature_flags = 1200653 
        
        # Add Supported Formats
        fmt = mp.supported_formats.add()
        fmt.format = "wav"
        fmt.sample_rate = 16000
        fmt.num_channels = 1
        fmt.sample_bytes = 2
        
        self._send(mp, 63)

        # Add Select for Pipeline
        sel_pipeline = pb2.ListEntitiesSelectResponse()
        sel_pipeline.object_id = "pipeline"
        sel_pipeline.key = 2
        sel_pipeline.name = "Pipeline"
        sel_pipeline.entity_category = 1 # CONFIG
        sel_pipeline.options.extend(["default"]) 
        self._send(sel_pipeline, 52) # Correct ID 52


        # Add Switch for Mute
        sw_mute = pb2.ListEntitiesSwitchResponse()
        sw_mute.object_id = "mute"
        sw_mute.key = 4
        sw_mute.name = "Mute Microphone"
        sw_mute.entity_category = 1 # CONFIG
        self._send(sw_mute, 17) # Correct ID 17
        
        # Add Assist Satellite Binary Sensor (or Sensor?)
        bs_assist = pb2.ListEntitiesBinarySensorResponse()
        bs_assist.object_id = "assist_active"
        bs_assist.key = 5
        bs_assist.name = "Assist Active"
        bs_assist.entity_category = 2 # DIAGNOSTIC
        self._send(bs_assist, 12)

        self._send(pb2.ListEntitiesDoneResponse(), 19) 

    def _handle_voice_assistant_request(self, req):
        _LOGGER.info("HA requested Voice Assistant Start: start=%s", req.start)
        if req.start:
            if self.websocket_server:
                asyncio.run_coroutine_threadsafe(
                    self.websocket_server.notify_start_listening(), 
                    self.loop
                )

    async def send_audio_chunk(self, chunk: bytes):
        """Send audio chunk to HA."""
        if self.protocol and self._connected:
            _LOGGER.debug("Sending audio chunk: %d bytes", len(chunk)) # Too noisy
            msg = pb2.VoiceAssistantAudio()
            msg.data = chunk
            self._send(msg, 106) # ID 106 

    def _handle_voice_assistant_configuration_request(self, req):
        """Handle request for current voice assistant configuration."""
        resp = pb2.VoiceAssistantConfigurationResponse()
        
        # Populate available wake words with HA STANDARD IDs
        ww1 = resp.available_wake_words.add()
        ww1.wake_word = "okay_nabu"
        if hasattr(ww1, "wake_word_id"):
             ww1.wake_word_id = "okay_nabu"
        elif hasattr(ww1, "id"):
             ww1.id = "okay_nabu"
             
        ww2 = resp.available_wake_words.add()
        ww2.wake_word = "alexa"
        if hasattr(ww2, "wake_word_id"):
             ww2.wake_word_id = "alexa"
        elif hasattr(ww2, "id"):
             ww2.id = "alexa"
        
        # Set active wake word (Default or currently selected)
        if not hasattr(self, 'current_wake_word'):
            self.current_wake_word = "okay_nabu_v0.1"
            
        # Map Internal Client ID -> HA Standard ID
        ha_active = self._map_ww_to_ha(self.current_wake_word)
        resp.active_wake_words.append(ha_active)
        resp.max_active_wake_words = 1
        
        self._send(resp, 122)

    def _handle_voice_assistant_set_configuration(self, req):
        """Handle request to set voice assistant configuration."""
        # Note: req.active_wake_words is a list in modern Protocol
        # _LOGGER.info(f"DEBUG: SetConfig Type: {type(req)}")
        # _LOGGER.info(f"DEBUG: SetConfig Dir: {dir(req)}")
        
        ha_ww = None
        
        # Try plural first (Modern)
        if req.active_wake_words:
            ha_ww = req.active_wake_words[0]
            _LOGGER.info("Received SetConfiguration (Plural): wake_word=%s", ha_ww)
        # Try singular (Legacy/Fallback)
        elif hasattr(req, 'active_wake_word') and req.active_wake_word:
             ha_ww = req.active_wake_word
             _LOGGER.info("Received SetConfiguration (Singular): wake_word=%s", ha_ww)
        else:
             _LOGGER.warning("Received SetConfiguration with empty wake words list & no singular field")
             return
        
        # Map HA Standard ID -> Internal Client ID
        self.current_wake_word = self._map_ww_to_client(ha_ww)
        
        # Notify WebSocket client with Client ID
        if self.websocket_server:
            asyncio.run_coroutine_threadsafe(
                self.websocket_server.broadcast_message({
                    "type": "config_update",
                    "wake_word": self.current_wake_word
                }),
                self.loop
            )
        
        # Send updated config back to HA to confirm
        self._handle_voice_assistant_configuration_request(None)



    async def _play_media_url(self, url: str):
        """Fetch audio from URL and broadcast to client."""
        try:
            import aiohttp
            _LOGGER.info("Fetching media from: %s", url)
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.read()
                        _LOGGER.info("Media fetched (%d bytes), broadcasting...", len(data))
                        if self.websocket_server:
                            await self.websocket_server.broadcast_audio(data)
                        
                        # Send state update: PLAYING
                        mp = pb2.MediaPlayerStateResponse()
                        mp.key = 1
                        mp.state = 2 # PLAYING
                        mp.volume = 0.5
                        mp.muted = False
                        self._send(mp, 64)
                        
                        # Wait for duration? Or just let it play.
                        # Ideally we check duration, but for now just wait a bit or let it stay playing?
                        # Better to reset to IDLE after a short delay or assumes client handles logic?
                        # I'll just leave it PLAYING for now, user can send IDLE if needed, or I'll implement "finished" later.
                        # Actually, better to send IDLE immediately after sending data? No, valid playback takes time.
                        # Let's just send IDLE after 1 second for short clips.
                        await asyncio.sleep(2) 
                        mp.state = 1 # IDLE
                        self._send(mp, 64)

                    else:
                        _LOGGER.error("Failed to fetch media: %s", resp.status)
        except Exception as e:
            _LOGGER.error("Error playing media: %s", e)

    def _handle_subscribe_states(self):
        # Send initial states
        # Media Player (1)
        mp_state = pb2.MediaPlayerStateResponse()
        mp_state.key = 1
        mp_state.state = 1 # 0=NONE (Error), 1=IDLE/PLAYING?
        # aioesphomeapi.MediaPlayerState: IDLE=0, PLAYING=1, PAUSED=2
        mp_state.volume = 0.5
        mp_state.muted = False
        self._send(mp_state, 64)

        # Pipeline Select (2)
        sel_state = pb2.SelectStateResponse()
        sel_state.key = 2
        sel_state.state = "default"
        self._send(sel_state, 53) # Correct ID 53

        # Wake Word Select (3)
        ww_state = pb2.SelectStateResponse()
        ww_state.key = 3
        ww_state.state = "okay_nabu"
        self._send(ww_state, 53) # Correct ID 53

         # Mute Switch (4)
        sw_state = pb2.SwitchStateResponse()
        sw_state.key = 4
        sw_state.state = False
        self._send(sw_state, 26)

        # Assist Binary Sensor (5)
        bs_state = pb2.BinarySensorStateResponse()
        bs_state.key = 5
        bs_state.state = False
        self._send(bs_state, 21) # Correct ID 21

