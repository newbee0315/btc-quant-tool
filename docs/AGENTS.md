# 项目概览 (Project Overview)

本项目旨在开发一个集成了量化模型的比特币（BTC）数据分析与预测系统。核心功能包括获取 BTC 的历史与实时交易数据，利用机器学习模型实时预测未来 10分钟、30分钟及 60分钟的价格涨跌概率，并通过一个高度定制化的、类似币安风格的专业 Web 界面展示预测结果与市场状态。

项目目标用户为加密货币交易者与量化分析师，技术栈采用前后端分离架构：
- **前端**: Next.js / React (提供高性能、现代化的交互体验，应用 Antigravity UI/UX 设计)
- **后端**: FastAPI (Python) (负责数据处理、模型推理及 API 服务)
- **数据**: PostgreSQL + TimescaleDB (时序数据存储)

# 资源索引 (Resource Index)

以下为本地已有的核心技能与架构模板，可直接用于项目开发：

- **核心架构模板**:
  - [General_Project_Architecture_Template.md](/Users/weihui/Desktop/tools/vibe-coding-cn-main/i18n/en/documents/Templates%20and%20Resources/General_Project_Architecture_Template.md) (参考 "2️⃣ 数据科学/量化项目标准结构")

- **数据获取与处理 (Data & Crypto)**:
  - **CCXT**: [SKILL.md](/Users/weihui/Desktop/tools/vibe-coding-cn-main/i18n/en/skills/ccxt/SKILL.md) - 用于对接 100+ 交易所获取实时行情与历史数据。
  - **CoinGecko**: [SKILL.md](/Users/weihui/Desktop/tools/vibe-coding-cn-main/i18n/en/skills/coingecko/SKILL.md) - 获取丰富的历史市场数据与元数据。
  - **CryptoFeed**: [SKILL.md](/Users/weihui/Desktop/tools/vibe-coding-cn-main/i18n/en/skills/cryptofeed/SKILL.md) - 高性能实时 WebSocket 数据流处理。

- **数据库 (Database)**:
  - **PostgreSQL**: [SKILL.md](/Users/weihui/Desktop/tools/vibe-coding-cn-main/i18n/en/skills/postgresql/SKILL.md) - 通用关系型数据存储。
  - **TimescaleDB**: [SKILL.md](/Users/weihui/Desktop/tools/vibe-coding-cn-main/i18n/en/skills/timescaledb/SKILL.md) - 专为时间序列数据（价格、K线）优化的 PostgreSQL 扩展。

# 缺失技能与获取 (Missing Skills & Acquisition)

以下技能在本地库中未找到，建议通过 SkillsMP 获取以增强项目能力：

1.  **UI/UX 设计专家 (UI/UX Design)**
    - **名称**: `ui-ux-pro-max-skill` (Antigravity Kit UI/UX 设计智能工具包)
    - **用途**: 用于设计直观、专业的量化仪表盘界面，生成设计系统与配色方案。
    - **获取方式**: 在 SkillsMP 搜索 `ui-ux-pro-max-skill` 或访问 [GitHub 仓库](https://github.com/nextlevelbuilder/ui-ux-pro-max-skill)。

2.  **机器学习/深度学习框架 (Machine Learning)**
    - **建议**: 搜索 `scikit-learn`, `pytorch` 或 `tensorflow` 相关技能，辅助模型训练与评估。

# 推荐 MCP 服务器 (Recommended MCP Servers)

为了实现数据持久化、版本控制及外部交互，建议配置以下 MCP 服务器：

### 1. 数据库 (PostgreSQL)
用于存储历史 K 线数据、实时价格流及模型预测记录。

- **Server**: `postgresql`
- **仓库**: [https://github.com/modelcontextprotocol/servers/tree/main/src/postgres](https://github.com/modelcontextprotocol/servers/tree/main/src/postgres)
- **配置示例**:
  ```json
  {
    "mcpServers": {
      "postgres": {
        "command": "npx",
        "args": [
          "-y",
          "@modelcontextprotocol/server-postgres",
          "postgresql://user:password@localhost:5432/btc_quant_db"
        ]
      }
    }
  }
  ```

### 2. 版本控制 (Git)
用于代码版本管理与协作。

- **Server**: `git`
- **仓库**: [https://github.com/modelcontextprotocol/servers/tree/main/src/git](https://github.com/modelcontextprotocol/servers/tree/main/src/git)
- **注意**: Git MCP Server 是 Python 包，请先运行 `python3 -m pip install mcp-server-git` 安装。
- **配置示例**:
  ```json
  {
    "mcpServers": {
      "git": {
        "command": "/Library/Frameworks/Python.framework/Versions/3.10/bin/python3",
        "args": [
          "-m",
          "mcp_server_git",
          "--repository",
          "/Users/weihui/Desktop/币安工具"
        ]
      }
    }
  }
  ```

### 3. 文件系统 (Filesystem)
允许智能体直接读写本地项目文件（通常 IDE 内置，若需显式配置可参考）。

- **Server**: `filesystem`
- **仓库**: [https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem](https://github.com/modelcontextprotocol/servers/tree/main/src/filesystem)
- **配置示例**:
  ```json
  {
    "mcpServers": {
      "filesystem": {
        "command": "npx",
        "args": [
          "-y",
          "@modelcontextprotocol/server-filesystem",
          "/Users/weihui/Desktop/币安工具"
        ]
      }
    }
  }
  ```

# 实施路线图 (Implementation Roadmap)

1.  **项目初始化 (Initialization)**
    - 基于“数据科学/量化项目标准结构”创建项目目录。
    - 配置 Python 虚拟环境及 `requirements.txt` (包含 `ccxt`, `pandas`, `scikit-learn` 等)。

2.  **数据基础设施 (Data Infrastructure)**
    - 部署 PostgreSQL + TimescaleDB。
    - 编写数据采集脚本（使用 `ccxt`），实现历史数据回补与实时数据 WebSocket 接入。

3.  **模型开发 (Model Development)**
    - 特征工程：计算技术指标（MA, RSI, MACD, Volatility 等）。
    - 训练预测模型：针对 10m/30m/60m 不同时间窗口训练分类模型（涨/跌）。
    - 模型评估与回测。

4.  **可视化与交互 (Visualization & UI)**
    - 使用 React/Next.js 构建币安风格前端界面。
    - 集成实时价格图表与模型预测概率仪表盘。
    - 接入 `ui-ux-pro-max-skill` 生成设计系统并落地到前端实现。

5.  **部署与监控 (Deployment)**
    - 容器化应用 (Docker)。
    - 设置定时任务或守护进程运行数据流与模型推理。
