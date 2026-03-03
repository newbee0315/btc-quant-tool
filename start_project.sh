#!/bin/bash

# ==================================================
# 🚀 币安工具项目一键启动脚本 (One-Click Start/Restart)
# ==================================================

# Define colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${GREEN}==========================================${NC}"
echo -e "${YELLOW}>>> 正在初始化项目启动流程...${NC}"
echo -e "${GREEN}==========================================${NC}"

# 1. 终止旧进程 (Clean up old processes)
echo -e "\n${YELLOW}>>> [1/3] 正在清理旧进程...${NC}"

if [ -f "./stop_project.sh" ]; then
    chmod +x ./stop_project.sh
    ./stop_project.sh
else
    echo -e "${RED}⚠️  Warning: stop_project.sh not found! Trying manual cleanup...${NC}"
    kill_port 8000 "Backend API"
    kill_port 3000 "Frontend UI"
    pkill -f "run_multicoin_bot.py" || true
    pkill -f "auto_optimizer.py" || true
fi

sleep 2

# 2. 启动后端 (Start Backend)
echo -e "\n${YELLOW}>>> [2/3] 正在启动后端 API (Python/Uvicorn)...${NC}"

# Check for virtual environment and activate it
if [ -d ".venv" ]; then
    echo -e "${YELLOW}>>> 检测到虚拟环境 (.venv)，正在激活...${NC}"
    source .venv/bin/activate
elif [ -d "venv" ]; then
    echo -e "${YELLOW}>>> 检测到虚拟环境 (venv)，正在激活...${NC}"
    source venv/bin/activate
fi

# Check if requirements are installed (optional check, skipping for speed)
# pip install -r requirements.txt

# Removed --reload for better stability in production
nohup uvicorn src.api.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo -e "${GREEN}✅ 后端已启动! (PID: $BACKEND_PID)${NC}"
echo -e "📄 日志文件: $(pwd)/backend.log"

# 3. 启动实盘交易机器人 (Start Trading Bot)
echo -e "\n${YELLOW}>>> [3/5] 正在启动实盘交易机器人 (run_multicoin_bot.py)...${NC}"
nohup python scripts/run_multicoin_bot.py > multicoin_bot.log 2>&1 &
BOT_PID=$!
echo -e "${GREEN}✅ 交易机器人已启动! (PID: $BOT_PID)${NC}"
echo -e "📄 日志文件: $(pwd)/multicoin_bot.log"

# 4. 启动自动优化器 (Start Auto Optimizer)
echo -e "\n${YELLOW}>>> [4/5] 正在启动自动优化器 (auto_optimizer.py)...${NC}"
nohup python scripts/auto_optimizer.py > auto_optimizer.log 2>&1 &
OPT_PID=$!
echo -e "${GREEN}✅ 自动优化器已启动! (PID: $OPT_PID)${NC}"
echo -e "📄 日志文件: $(pwd)/auto_optimizer.log"

# 5. 启动前端 (Start Frontend)
echo -e "\n${YELLOW}>>> [5/5] 正在启动前端界面 (Next.js)...${NC}"

cd frontend
nohup npm run dev > ../frontend.log 2>&1 &
FRONTEND_PID=$!
cd ..

echo -e "${GREEN}✅ 前端已启动! (PID: $FRONTEND_PID)${NC}"
echo -e "📄 日志文件: $(pwd)/frontend.log"

# Summary
echo -e "\n${GREEN}==========================================${NC}"
echo -e "${GREEN}🎉 项目启动成功! (Project Started Successfully)${NC}"
echo -e "${GREEN}==========================================${NC}"
echo -e "🌍 后端 API文档: \033[4;34mhttp://localhost:8000/docs\033[0m"
echo -e "🌍 前端访问地址: \033[4;34mhttp://localhost:3000\033[0m"
echo -e "------------------------------------------"
echo -e "💡 查看日志命令:"
echo -e "   tail -f backend.log"
echo -e "   tail -f frontend.log"
echo -e "------------------------------------------"
