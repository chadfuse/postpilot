#!/bin/bash
# Start all PostPilot services in background

echo "Starting PostPilot services..."

# Kill any existing processes
pkill -f "uvicorn app.api" 2>/dev/null
pkill -f "app.worker" 2>/dev/null
pkill -f "streamlit run" 2>/dev/null
sleep 1

# Start API + Scheduler
python3 -m uvicorn app.api:app --host 0.0.0.0 --port 8000 &
API_PID=$!
echo "API + Scheduler started (PID: $API_PID)"

sleep 2

# Start Worker
python3 -m app.worker &
WORKER_PID=$!
echo "Worker started (PID: $WORKER_PID)"

sleep 1

# Start Dashboard
streamlit run dashboard/streamlit_app.py --server.port 8501 &
DASH_PID=$!
echo "Dashboard started (PID: $DASH_PID)"

echo ""
echo "All services running:"
echo "  API + Scheduler: http://localhost:8000"
echo "  Dashboard:       http://localhost:8501"
echo ""
echo "To stop all: pkill -f uvicorn; pkill -f app.worker; pkill -f streamlit"

wait
