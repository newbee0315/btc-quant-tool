#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "🚀 Starting Daily Data Update & Model Retraining..."
echo "📂 Project Root: $PROJECT_ROOT"

# Ensure we are in the project root
cd "$PROJECT_ROOT"

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Run the daily task python script
# Using the python executable from the current environment or .venv
if [ -d ".venv" ]; then
    PYTHON_EXEC=".venv/bin/python"
else
    PYTHON_EXEC="python3"
fi

echo "🐍 Using Python: $PYTHON_EXEC"
$PYTHON_EXEC src/scheduler/daily_task.py

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Daily Update Completed Successfully."
else
    echo "❌ Daily Update Failed with exit code $EXIT_CODE."
fi

exit $EXIT_CODE
