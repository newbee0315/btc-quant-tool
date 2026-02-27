# BTC Quant Tool (币安工具)

![Project Status](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![Next.js](https://img.shields.io/badge/Next.js-15-black)

## 📖 项目概览 (Project Overview)

本项目是一个集成了量化模型的比特币（BTC）及多币种数据分析与预测系统。核心功能包括获取 BTC 及 Top 30 主流币种的历史与实时交易数据，利用机器学习模型（XGBoost/RandomForest）实时预测未来 10分钟、30分钟及 60分钟的价格涨跌概率，并通过一个高度定制化的、类似币安风格的专业 Web 界面展示预测结果与市场状态。

### 最新特性 (New Features)
*   **多币种支持**: 扩展支持 **14 个主流币种**（BTC, ETH, SOL, BNB, DOGE, XRP, PEPE, AVAX, LINK, ADA, TRX, LDO, BCH, OP）的实时监控与交易。
*   **全历史数据聚合**: 修复了 PnL 和胜率计算问题，现在能正确汇总所有监控币种的历史交易数据。
*   **智能防限流**: 实现了 **顺序初始化 (Sequential Initialization)** 机制，避免启动时触发交易所 API 频率限制 (429/IP Ban)。
*   **动态风控**: 
    *   无需手动设置单一仓位限制，系统根据账户总权益（Equity）和风险偏好自动计算仓位。
    *   **2% 硬止损**: 强制执行每笔交易最大 2% 的亏损限制，保护本金。

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
*   **工具 (Tools)**: APScheduler (定时任务)

## 🚀 快速开始 (Quick Start)

### 前置要求 (Prerequisites)

*   [Python 3.10+](https://www.python.org/)
*   [Node.js 18+](https://nodejs.org/)

### 配置 (Configuration)

1.  复制配置模板:
    ```bash
    cp trader_config.example.json trader_config.json
    ```
2.  编辑 `trader_config.json`，填入你的 Binance API Key 和 Secret（注意：不要将包含真实 Key 的文件上传到 Git）：
    ```json
    {
        "api_key": "your_api_key",
        "api_secret": "your_api_secret",
        ...
    }
    ```
    或者使用环境变量：
    ```bash
    export BINANCE_API_KEY="your_key"
    export BINANCE_API_SECRET="your_secret"
    ```

> 安全提示：仓库已在 `.gitignore` 中忽略了 `.env` 与 `trader_config.json`。如曾误提交敏感文件，请执行 `git rm --cached <文件>` 后再提交。

### 本地启动 (Local Setup)

#### 1. 后端 Setup

```bash
# 1. 创建虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装依赖
pip install -r requirements.txt

# 3. 运行后端 API 服务
python src/api/main.py
```
后端 API 地址: http://localhost:8000/docs

#### 2. 前端 Setup

```bash
cd frontend
npm install
npm run dev
```
前端访问地址: http://localhost:3000

#### 3. 启动实盘交易机器人 (Multi-Coin Bot)

```bash
# 在新的终端窗口中运行
source .venv/bin/activate
python scripts/run_multicoin_bot.py
```

*   单实例防重：内置锁文件 `/tmp/btc_quant_multicoin.lock`，避免重复进程引发下单冲突与 API 限流。
*   启动策略：顺序初始化各币种 Trader（每币 1s），降低 429/418 风险。
*   风控核心：支持全局风险上限（max_portfolio_leverage，1~10x），相关性过滤（默认阈值 0.65），单币/同向敞口上限等。

## 📂 目录结构 (Directory Structure)

```
.
├── configs/            # 配置文件
├── docs/               # 项目文档 (架构说明)
├── frontend/           # Next.js 前端项目
├── scripts/            # 运维与工具脚本
├── src/                # 后端核心代码
│   ├── api/            # FastAPI 接口
│   ├── backtest/       # 回测引擎
│   ├── data/           # 数据采集模块
│   ├── models/         # 机器学习模型 (训练/预测)
│   ├── notification/   # 消息推送 (飞书)
│   └── trader/         # 模拟交易引擎
└── requirements.txt    # Python 依赖
```

## 🔐 安全与合规 (Security)

- 切勿将以下文件提交到 Git：
  - `.env`、`.env.*`
  - `trader_config.json`（包含 `api_key`、`api_secret`）
- 校验是否被跟踪：
  ```bash
  git ls-files --error-unmatch .env || echo "NOT TRACKED"
  git ls-files --error-unmatch trader_config.json || echo "NOT TRACKED"
  ```
- 若误加入 Git 历史：
  ```bash
  git rm --cached .env trader_config.json
  echo -e "\n.env\ntrader_config.json" >> .gitignore
  git commit -m "chore: remove secrets from repo"
  ```

## ⛑ 稳定性 (Resilience)

- 时间同步自愈：检测到 `-1021 Timestamp ahead` 时，主动调用交易所时间 `fetch_time()` 计算 `timeDifference` 并重试，避免签名失败。
- Watchdog：后端定时任务每 30 分钟巡检核心作业与机器人心跳；机器人日志 60 分钟内有更新视为健康。

## 📝 许可证 (License)

MIT License
