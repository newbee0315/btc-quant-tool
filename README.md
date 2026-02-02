# BTC Quant Tool (币安工具)

![Project Status](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Next.js](https://img.shields.io/badge/Next.js-15-black)
![Docker](https://img.shields.io/badge/Docker-Supported-blue)

## 📖 项目概览 (Project Overview)

本项目是一个集成了量化模型的比特币（BTC）数据分析与预测系统。核心功能包括获取 BTC 的历史与实时交易数据，利用机器学习模型（XGBoost/RandomForest）实时预测未来 10分钟、30分钟及 60分钟的价格涨跌概率，并通过一个高度定制化的、类似币安风格的专业 Web 界面展示预测结果与市场状态。

### 核心功能 (Key Features)

*   **实时监控**: 毫秒级获取 BTC/USDT 实时行情。
*   **AI 预测**: 基于历史数据训练机器学习模型，预测未来 10m/30m/60m 走势。
    *   动态阈值系统：自动寻找高置信度预测区间。
    *   多维度特征工程：集成 RSI, MACD, Bollinger Bands, ATR 等技术指标。
*   **模拟交易 (Paper Trading)**: 内置模拟交易引擎，支持自动跟随 AI 信号进行开仓/平仓，验证策略有效性。
*   **智能通知**: 集成飞书 (Feishu/Lark) 机器人，当出现高置信度信号时自动推送提醒。
*   **专业可视化**: 使用 Next.js + Antigravity UI 构建的现代化仪表盘，支持 TradingView 风格 K 线图。

## 🛠 技术栈 (Tech Stack)

*   **前端 (Frontend)**: Next.js 15, React, Tailwind CSS, Lucide Icons, Recharts
*   **后端 (Backend)**: FastAPI, Uvicorn, WebSocket
*   **数据科学 (Data Science)**: Pandas, NumPy, Scikit-learn, XGBoost, TA-Lib (Technical Analysis)
*   **基础设施 (Infra)**: Docker, Docker Compose
*   **工具 (Tools)**: APScheduler (定时任务), Expect (自动化部署)

## 🚀 快速开始 (Quick Start)

### 前置要求 (Prerequisites)

*   [Docker](https://www.docker.com/) & Docker Compose
*   [Python 3.10+](https://www.python.org/) (用于本地开发)
*   [Node.js 18+](https://nodejs.org/) (用于本地开发)

### 使用 Docker 启动 (Recommended)

只需一条命令即可启动整个堆栈（前端 + 后端）：

```bash
docker-compose up --build -d
```

*   **前端访问**: http://localhost:3000
*   **后端 API**: http://localhost:8000/docs

### 本地开发 (Local Development)

#### 后端 Setup

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行后端
python src/api/main.py
```

#### 前端 Setup

```bash
cd frontend
npm install
npm run dev
```

## 📂 目录结构 (Directory Structure)

```
.
├── configs/            # 配置文件
├── docs/               # 项目文档 (部署笔记, 架构说明)
├── frontend/           # Next.js 前端项目
├── scripts/            # 运维与工具脚本
├── src/                # 后端核心代码
│   ├── api/            # FastAPI 接口
│   ├── backtest/       # 回测引擎
│   ├── data/           # 数据采集模块
│   ├── models/         # 机器学习模型 (训练/预测)
│   ├── notification/   # 消息推送 (飞书)
│   └── trader/         # 模拟交易引擎
├── Dockerfile.backend  # 后端构建文件
├── Dockerfile.frontend # 前端构建文件
├── docker-compose.yml  # 容器编排
└── requirements.txt    # Python 依赖
```

## 🚢 部署 (Deployment)

详细部署指南请参考 [docs/DEPLOYMENT_NOTES.md](docs/DEPLOYMENT_NOTES.md)。

本项目支持一键部署到云服务器（如阿里云），包含自动化打包脚本和环境配置说明。

## 📝 许可证 (License)

MIT License
