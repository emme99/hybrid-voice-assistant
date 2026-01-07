#!/bin/bash
# Quick setup script for Hybrid Voice Satellite

set -e

echo "🎙️ Hybrid Voice Satellite - Quick Setup"
echo "========================================"
echo

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 not found. Please install Python 3.11 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
echo "✓ Found Python $PYTHON_VERSION"

# Setup server
echo
echo "📦 Setting up Python server..."
cd server

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

echo "✓ Server dependencies installed"

# Create config from example
if [ ! -f "config.yaml" ]; then
    echo "Creating config.yaml from example..."
    cp config.example.yaml config.yaml
    echo
    echo "⚠️  Please edit server/config.yaml with your Home Assistant details:"
    echo "   - home_assistant.host: Your HA hostname or IP"
    echo "   - server.auth_token: Change the default token!"
    echo
fi

cd ..

# Setup client
echo
echo "🌐 Setting up web client..."
echo "✓ Client files ready (no build required)"

# Check for HTTPS certificates
echo
echo "🔒 HTTPS Setup"
echo "For microphone access, the client must be served over HTTPS."
echo

if [ ! -f "client/cert.pem" ]; then
    echo "Would you like to generate self-signed certificates for testing? (yes/no)"
    read -r response
    if [ "$response" = "yes" ]; then
        openssl req -x509 -newkey rsa:4096 -keyout client/key.pem \
            -out client/cert.pem -days 365 -nodes \
            -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
        echo "✓ Self-signed certificates created in client/ directory"
    fi
fi

echo
echo "✅ Setup complete!"
echo
echo "📝 Next steps:"
echo "1. Edit server/config.yaml with your Home Assistant details"
echo "2. Start the server: cd server && source venv/bin/activate && python main.py"
echo "3. Open the client in your browser"
echo "   - Local: file://$(pwd)/client/index.html"
echo "   - HTTPS: Use a local web server (python -m http.server)"
echo
echo "For Docker deployment: docker-compose up -d"
echo
