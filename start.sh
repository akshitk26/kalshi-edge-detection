#!/bin/bash
# Start both backend and frontend servers

echo "Starting backend API server on :5050..."
python3 -m edge_engine.api_server &
BACKEND_PID=$!

# Wait briefly for backend to be ready
sleep 2

echo "Starting frontend dev server..."
cd frontend && npm run dev &
FRONTEND_PID=$!

# Trap Ctrl+C to kill both
trap "echo 'Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM

echo ""
echo "Backend PID:  $BACKEND_PID"
echo "Frontend PID: $FRONTEND_PID"
echo "Press Ctrl+C to stop both."
echo ""

wait
