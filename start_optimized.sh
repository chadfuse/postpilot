#!/bin/bash
# Start PostPilot with memory optimization

echo "Starting PostPilot (memory-optimized)..."

# Kill any existing processes
pkill -f "uvicorn" 2>/dev/null
pkill -f "streamlit" 2>/dev/null
sleep 1

# Set memory optimization environment variables
export PYTHONOPTIMIZE=1
export PYTHONUNBUFFERED=1

# Start API with optimized module (single process, no workers)
echo "Starting API server (optimized)..."
python3 -c "
import uvicorn
from app.api_optimized import app
uvicorn.run(app, host='0.0.0.0', port=8000, workers=1, limit_concurrency=10, limit_max_requests=1000)
" &
API_PID=$!

sleep 3

# Start dashboard (lightweight)
echo "Starting dashboard..."
streamlit run dashboard/streamlit_app.py --server.port 8501 --server.headless true &
DASH_PID=$!

echo ""
echo "PostPilot started (memory-optimized):"
echo "  API:        http://localhost:8000"
echo "  Dashboard:  http://localhost:8501"
echo ""
echo "Memory optimizations active:"
echo "  - Lazy module loading"
echo "  - Response caching"
echo "  - Single API worker"
echo "  - No background worker processes"
echo ""
echo "To stop: pkill -f uvicorn; pkill -f streamlit"

wait
