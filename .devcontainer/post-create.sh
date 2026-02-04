#!/bin/bash
# Post-create script for DevContainer

set -e

echo "🔧 Setting up Integrador development environment..."

# Backend setup
echo "📦 Installing Python dependencies..."
cd /workspace/backend
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -r requirements-dev.txt 2>/dev/null || echo "No requirements-dev.txt found"

# Install CLI dependencies
pip install typer rich httpx websockets

# Frontend setup
echo "📦 Installing Dashboard dependencies..."
cd /workspace/Dashboard
npm install

echo "📦 Installing pwaMenu dependencies..."
cd /workspace/pwaMenu
npm install

echo "📦 Installing pwaWaiter dependencies..."
cd /workspace/pwaWaiter
npm install

# Create env files if not exist
echo "📝 Setting up environment files..."
cd /workspace

if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env 2>/dev/null || echo "No .env.example found"
fi

if [ ! -f Dashboard/.env ]; then
    echo "VITE_API_URL=http://localhost:8000" > Dashboard/.env
    echo "VITE_WS_URL=ws://localhost:8001" >> Dashboard/.env
fi

if [ ! -f pwaMenu/.env ]; then
    echo "VITE_API_URL=http://localhost:8000" > pwaMenu/.env
    echo "VITE_WS_URL=ws://localhost:8001" >> pwaMenu/.env
fi

if [ ! -f pwaWaiter/.env ]; then
    echo "VITE_API_URL=http://localhost:8000" > pwaWaiter/.env
    echo "VITE_WS_URL=ws://localhost:8001" >> pwaWaiter/.env
fi

echo "✅ Development environment setup complete!"
