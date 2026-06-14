#!/bin/bash
# Quick development run script

echo "🚀 Starting TA Data Analysis Agent (Development Mode)"
echo ""

# Check if Ollama is running
if curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "✅ Ollama is running"
    ollama list 2>/dev/null | head -5
else
    echo "⚠️  Ollama not detected. Starting via Docker..."
    docker compose up -d ollama
    echo "   Waiting for Ollama to start..."
    sleep 5
fi

echo ""

# Activate venv
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [ -d "venv" ]; then
    source venv/bin/activate
    echo "✅ Python venv activated"
else
    echo "❌ venv not found. Run scripts/setup_environment.sh first."
    exit 1
fi

# Run backend
echo ""
echo "🌐 Starting FastAPI backend on http://localhost:8000"
echo "📖 API docs at http://localhost:8000/docs"
echo ""
cd backend
uvicorn main:app --reload --host 0.0.0.0 --port 8000
