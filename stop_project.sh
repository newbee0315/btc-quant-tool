#!/bin/bash

echo ">>> Stopping all services..."

# Function to kill process on a specific port
kill_port() {
    local port=$1
    local name=$2
    local pid=$(lsof -t -i:$port)
    
    if [ -n "$pid" ]; then
        echo "Stopping $name (PID: $pid)..."
        kill -9 $pid
        echo "✅ $name stopped."
    else
        echo "✅ $name is not running."
    fi
}

# Function to kill python process by name
kill_py_script() {
    local script=$1
    local name=$2
    local pid=$(ps aux | grep "$script" | grep -v grep | awk '{print $2}')
    
    if [ -n "$pid" ]; then
        echo "Stopping $name (PID: $pid)..."
        # Handle multiple PIDs (e.g., if multiple instances running)
        echo "$pid" | xargs kill -9
        echo "✅ $name stopped."
    else
        echo "✅ $name is not running."
    fi
}

echo "Stopping existing Backend API..."
pkill -f -i "uvicorn src.api.main:app" || true
pkill -f -i "python.*src/api/main.py" || true
kill_port 3000 "Frontend UI (Next.js)"
kill_port 8501 "Frontend UI (Streamlit)"
pkill -f -i "streamlit run webui.py" || true

echo "Stopping existing Trading Bot..."
pkill -f -i "python.*run_multicoin_bot.py" || true

echo "Stopping existing Auto Optimizer..."
pkill -f -i "python.*auto_optimizer.py" || true

echo ">>> All services stopped successfully."
