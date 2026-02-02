#!/bin/bash

# 阿里云部署自动化脚本
# 用法: chmod +x deploy_aliyun.sh && ./deploy_aliyun.sh

set -e  # 遇到错误立即停止

echo "==========================================="
echo "   Binance AI Tool - Aliyun Deployment"
echo "==========================================="

# 1. 检查并安装 Docker
if ! command -v docker &> /dev/null; then
    echo "Logs: Docker 未找到，正在通过阿里云镜像源安装..."
    curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
    
    echo "Logs: 启动 Docker 服务..."
    sudo systemctl enable docker
    sudo systemctl start docker
else
    echo "Logs: Docker 已安装，版本: $(docker --version)"
fi

# 2. 检查 Docker Compose
# 现代 Docker 安装通常包含 'docker compose' 子命令
if docker compose version &> /dev/null; then
    echo "Logs: Docker Compose (Plugin) 已安装"
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &> /dev/null; then
    echo "Logs: Docker Compose (Standalone) 已安装"
    COMPOSE_CMD="docker-compose"
else
    echo "Logs: 未找到 Docker Compose，正在安装..."
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.6/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    sudo ln -s /usr/local/bin/docker-compose /usr/bin/docker-compose
    COMPOSE_CMD="docker-compose"
fi

# 2.5 配置环境变量 (自动设置服务器 IP)
SERVER_IP="106.15.73.181"
echo "Logs: 配置环境变量 (API URL: http://${SERVER_IP}:8000)..."
if [ -f .env ]; then
    # 如果 .env 存在，更新或追加 NEXT_PUBLIC_API_URL
    if grep -q "NEXT_PUBLIC_API_URL" .env; then
        # 使用 | 作为分隔符避免 URL 中的 / 冲突
        sed -i "s|NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000|" .env
    else
        echo "" >> .env
        echo "NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000" >> .env
    fi
else
    # 如果 .env 不存在，创建它
    echo "NEXT_PUBLIC_API_URL=http://${SERVER_IP}:8000" > .env
fi

# 2.6 修复 Docker 挂载文件问题 (paper_trading_state.json)
# 防止 Docker 自动创建为目录
if [ ! -f paper_trading_state.json ]; then
    echo "Logs: 检测到 paper_trading_state.json 缺失，正在创建空文件..."
    echo "{}" > paper_trading_state.json
elif [ -d paper_trading_state.json ]; then
    echo "Logs: 检测到 paper_trading_state.json 是目录，正在修正..."
    rm -rf paper_trading_state.json
    echo "{}" > paper_trading_state.json
fi

# 3. 停止旧容器（如果有）
echo "Logs: 正在清理旧容器..."
$COMPOSE_CMD down --remove-orphans || true

# 4. 构建并启动新容器
echo "Logs: 正在构建并启动服务（这可能需要几分钟）..."
$COMPOSE_CMD up -d --build

# 5. 检查状态
echo "Logs: 检查服务状态..."
if $COMPOSE_CMD ps | grep -q "Up"; then
    echo "==========================================="
    echo "✅ 部署成功！"
    echo "==========================================="
    
    # 尝试获取公网 IP
    PUBLIC_IP=$(curl -s ifconfig.me || echo "您的服务器IP")
    
    echo "访问地址:"
    echo "  - 前端页面: http://${PUBLIC_IP}:3000"
    echo "  - 后端文档: http://${PUBLIC_IP}:8000/docs"
    echo ""
    echo "⚠️  注意: 请确保阿里云安全组已放行 3000 和 8000 端口 (TCP)"
else
    echo "❌ 部署可能存在问题，请运行 '$COMPOSE_CMD logs' 查看日志。"
fi
