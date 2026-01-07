"""
Hybrid Voice Satellite Server
Main entry point for the Python server component (ESPHome Protocol).
"""
import asyncio
import logging
import yaml
import signal
import sys
from pathlib import Path

# Import new ESPHome modules
from esphome import ESPHomeProtocolHandler, ESPHomeServerProtocol
from websocket_server import WebSocketServer


def load_config(config_path: str = "config.yaml") -> dict:
    config_file = Path(config_path)
    if not config_file.exists():
        example_config = Path("config.example.yaml")
        if example_config.exists():
            print(f"Config file not found, using {example_config}")
            config_file = example_config
        else:
            print("No configuration file found!")
            sys.exit(1)
    
    with open(config_file, 'r') as f:
        return yaml.safe_load(f)


def setup_logging(config: dict):
    log_level = config.get('logging', {}).get('level', 'INFO')
    log_file = config.get('logging', {}).get('file')
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file) if log_file else logging.NullHandler()
        ]
    )


async def main():
    """Main application entry point."""
    config = load_config()
    setup_logging(config)
    
    logger = logging.getLogger(__name__)
    logger.info("Starting Hybrid Voice Satellite Server (ESPHome Protocol)")
    
    server_config = config.get('server', {})
    
    # Initialize ESPHome Handler
    loop = asyncio.get_running_loop()
    esphome_handler = ESPHomeProtocolHandler(loop=loop)
    
    # Start ESPHome TCP Server (Port 6053)
    esphome_port = 6053
    esphome_host = '0.0.0.0'
    
    logger.info(f"Starting ESPHome API Server on {esphome_host}:{esphome_port}")
    esphome_server = await loop.create_server(
        lambda: ESPHomeServerProtocol(
            on_connect=esphome_handler.on_connect,
            on_message=esphome_handler.on_message
        ),
        esphome_host, esphome_port
    )
    
    # Initialize WebSocket server (Listens for Browsers)
    # Check for SSL certificates in client directory
    ssl_context = None
    # Use absolute path relative to this script
    current_dir = Path(__file__).parent.resolve()
    client_dir = current_dir.parent / "client"
    cert_file = client_dir / "cert.pem"
    key_file = client_dir / "key.pem"
    
    ssl_enabled = server_config.get('ssl', True)
    
    if ssl_enabled and cert_file.exists() and key_file.exists():
        import ssl
        logger.info(f"Loading SSL certificates from {cert_file}")
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(cert_file, key_file)
    else:
        if not ssl_enabled:
             logger.info("SSL disabled in configuration")
        else:
             logger.warning("No SSL certificates found. WebSocket will run in insecure mode (ws://)")
        
    ws_server = WebSocketServer(
        host=server_config.get('host', '0.0.0.0'),
        port=server_config.get('port', 8765),
        esphome_handler=esphome_handler,
        auth_token=server_config.get('auth_token'),
        ssl_context=ssl_context,
        client_config=config.get('client', {})
    )
    
    # Shutdown handler
    shutdown_event = asyncio.Event()
    
    def signal_handler(sig, frame):
        logger.info("Received shutdown signal")
        if shutdown_event.is_set():
            logger.warning("Forced shutdown...")
            sys.exit(1)
        shutdown_event.set()
        
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start WS Server
        await ws_server.start()
        
        # Keep running
        logger.info("Services started. Press Ctrl+C to stop.")
        while not shutdown_event.is_set():
             await asyncio.sleep(0.1)
        
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        logger.info("Shutting down...")
        try:
            esphome_server.close()
            await esphome_server.wait_closed()
            await ws_server.stop()
        except Exception as e:
            logger.error(f"Error during shutdown: {e}")
        logger.info("Shutdown complete")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Unexpected error: {e}")
