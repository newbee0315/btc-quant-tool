#!/bin/bash

# ==========================================
# Binance AI Tool - Cloud Deployment Script
# ==========================================
# This script syncs local code, data, and models to the cloud server
# and restarts the services using Docker Compose.

# --- Configuration ---
SERVER_IP="106.15.73.181"
REMOTE_USER="root"
REMOTE_DIR="/root/binance-tool"
SSH_PORT="22"

# --- Colors ---
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}🚀 Starting deployment to ${SERVER_IP}...${NC}"

# 1. Validation
if [ ! -f "requirements.txt" ]; then
    echo "⚠️ requirements.txt not found, generating..."
    pip3 freeze > requirements.txt
fi

# 2. Sync Files (Rsync)
echo -e "${YELLOW}📦 Syncing files to remote server...${NC}"
# We explicitly include data and saved_models to ensure consistency
# Exclude heavy/unnecessary folders
rsync -avz -e "ssh -p ${SSH_PORT}" \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude 'node_modules' \
    --exclude '.next' \
    --exclude '.DS_Store' \
    --exclude 'venv' \
    --exclude '.env' \
    --exclude 'tests' \
    --exclude 'tmp' \
    ./ ${REMOTE_USER}@${SERVER_IP}:${REMOTE_DIR}

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ File sync successful!${NC}"
else
    echo -e "❌ File sync failed. Please check SSH connection."
    exit 1
fi

# 3. Remote Execution
echo -e "${YELLOW}🔄 Building and restarting services on remote server...${NC}"
ssh -p ${SSH_PORT} ${REMOTE_USER}@${SERVER_IP} "bash -s" <<EOF
    cd ${REMOTE_DIR}
    
    # Ensure Docker is installed (Basic check)
    if ! command -v docker &> /dev/null; then
        echo "Docker not found. Please run scripts/deploy_aliyun.sh first to setup environment."
        exit 1
    fi

    # Create .env if missing (Simple check, ideally should be managed securely)
    if [ ! -f .env ]; then
        echo "Creating default .env..."
        echo "NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000" > .env
        echo "FEISHU_WEBHOOK_URL=" >> .env
    fi

    # Stop old containers
    docker compose down --remove-orphans

    # Build and Start
    # --build ensures the new code/data in the image is used
    docker compose up -d --build

    # Prune unused images to save space
    docker image prune -f
EOF

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Deployment Completed Successfully!${NC}"
    echo -e "Frontend: http://${SERVER_IP}:3000"
    echo -e "Backend:  http://${SERVER_IP}:8000/docs"
else
    echo -e "❌ Remote command execution failed."
    exit 1
fi
