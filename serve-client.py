#!/usr/bin/env python3
"""
Simple HTTPS server for testing the hybrid voice satellite client.
Browsers require HTTPS for microphone access.
"""
import http.server
import ssl
import os
import sys
from pathlib import Path

# Configuration
PORT = 8443
CERT_FILE = "cert.pem"
KEY_FILE = "key.pem"

def generate_self_signed_cert():
    """Generate self-signed certificate if it doesn't exist."""
    if os.path.exists(CERT_FILE) and os.path.exists(KEY_FILE):
        print(f"✓ Using existing certificates: {CERT_FILE}, {KEY_FILE}")
        return
    
    print("📜 Generating self-signed certificate...")
    import subprocess
    
    try:
        subprocess.run([
            'openssl', 'req', '-x509', '-newkey', 'rsa:4096',
            '-keyout', KEY_FILE, '-out', CERT_FILE,
            '-days', '365', '-nodes',
            '-subj', '/C=IT/ST=State/L=City/O=Dev/CN=localhost'
        ], check=True, capture_output=True)
        print(f"✓ Certificate generated: {CERT_FILE}")
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to generate certificate: {e}")
        print("\nManual command:")
        print(f"openssl req -x509 -newkey rsa:4096 -keyout {KEY_FILE} -out {CERT_FILE} -days 365 -nodes")
        sys.exit(1)
    except FileNotFoundError:
        print("❌ OpenSSL not found. Please install it or generate certificates manually.")
        sys.exit(1)

def main():
    # Change to client directory
    client_dir = Path(__file__).parent / "client"
    if client_dir.exists():
        os.chdir(client_dir)
        print(f"📁 Serving from: {client_dir}")
    else:
        print(f"❌ Client directory not found: {client_dir}")
        sys.exit(1)
    
    # Generate certificate if needed
    generate_self_signed_cert()
    
    # Setup HTTPS server
    server_address = ('localhost', PORT)
    httpd = http.server.HTTPServer(server_address, http.server.SimpleHTTPRequestHandler)
    
    # Wrap with SSL
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(CERT_FILE, KEY_FILE)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    
    print("\n" + "="*60)
    print("🎙️  Hybrid Voice Satellite - Client Server")
    print("="*60)
    print(f"\n✓ HTTPS server running on https://localhost:{PORT}")
    print("\n📝 Next steps:")
    print("   1. Open https://localhost:8443 in your browser")
    print("   2. Accept the self-signed certificate warning")
    print("   3. Click 'Activate Voice Control'")
    print("   4. Grant microphone permission")
    print("   5. Press SPACEBAR to simulate wake word")
    print("\n⚠️  Note: You'll see a security warning because the certificate")
    print("    is self-signed. This is normal for development.")
    print("\n🛑 Press Ctrl+C to stop the server")
    print("="*60 + "\n")
    
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n\n👋 Server stopped")
        sys.exit(0)

if __name__ == '__main__':
    main()
