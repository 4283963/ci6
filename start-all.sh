#!/bin/bash

set -e

echo "============================================"
echo "  Quant Risk System - All-in-One Starter"
echo "============================================"
echo ""

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[1/4] Starting infrastructure (Redis + TimescaleDB)..."
if command -v docker &> /dev/null; then
    docker-compose up -d
    echo "✓ Infrastructure containers started"
else
    echo "⚠ Docker not found, skipping infrastructure"
fi
echo ""

echo "[2/4] Starting quant-feed (Go)..."
cd "$SCRIPT_DIR/quant-feed"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  Created default .env for quant-feed"
fi
if [ ! -d "vendor" ] && [ ! -f "go.sum" ]; then
    go mod tidy
fi
go build -o quant-feed .
./quant-feed &
FEED_PID=$!
echo "✓ quant-feed started (PID: $FEED_PID)"
echo ""

echo "[3/4] Starting quant-calc (Python)..."
cd "$SCRIPT_DIR/quant-calc"
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  Created default .env for quant-calc"
fi
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "  Created virtual environment"
fi
source venv/bin/activate
pip install -q -r requirements.txt
python main.py &
CALC_PID=$!
echo "✓ quant-calc started (PID: $CALC_PID)"
echo ""

echo "[4/4] Starting quant-dashboard (React)..."
cd "$SCRIPT_DIR/quant-dashboard"
if [ ! -d "node_modules" ]; then
    npm install
fi
npm start &
DASH_PID=$!
echo "✓ quant-dashboard started (PID: $DASH_PID)"
echo ""

echo "============================================"
echo "  All services started!"
echo "============================================"
echo ""
echo "  Dashboard: http://localhost:3000"
echo "  WebSocket: ws://localhost:8080/ws"
echo "  Redis: localhost:6379"
echo "  TimescaleDB: localhost:5432"
echo ""
echo "  Press Ctrl+C to stop all services"
echo "============================================"

cleanup() {
    echo ""
    echo "Shutting down all services..."
    kill $FEED_PID 2>/dev/null || true
    kill $CALC_PID 2>/dev/null || true
    kill $DASH_PID 2>/dev/null || true
    
    if command -v docker &> /dev/null; then
        cd "$SCRIPT_DIR"
        docker-compose down
    fi
    
    echo "All services stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

wait
