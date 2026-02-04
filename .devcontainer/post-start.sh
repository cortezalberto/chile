#!/bin/bash
# Post-start script for DevContainer

set -e

echo "🚀 Starting Integrador services..."

# Activate Python venv
source /workspace/backend/.venv/bin/activate

# Run database migrations
echo "📊 Running database migrations..."
cd /workspace/backend
alembic upgrade head 2>/dev/null || echo "Alembic not configured or migrations not needed"

echo "✅ Services ready!"
echo ""
echo "Available commands:"
echo "  Backend API:    cd backend && uvicorn rest_api.main:app --reload"
echo "  WS Gateway:     cd backend && uvicorn ws_gateway.main:app --port 8001 --reload"
echo "  Dashboard:      cd Dashboard && npm run dev"
echo "  pwaMenu:        cd pwaMenu && npm run dev"
echo "  pwaWaiter:      cd pwaWaiter && npm run dev"
echo ""
echo "CLI available: python backend/cli.py --help"
