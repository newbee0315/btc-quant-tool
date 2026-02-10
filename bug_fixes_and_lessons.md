# 币安实盘交易系统 Bug 修复与经验总结
(Bug Fixes & Lessons Learned - Binance Real Trading System)

本文档记录了在实盘交易系统调试过程中遇到的关键问题、解决方案及技术细节，供后续开发参考。

## 1. 核心问题与修复 (Critical Fixes)

### 1.1 币安接口连接与代理配置
- **问题**: `ConnectionResetError` 或 `451 Unavailable For Legal Reasons`。
- **原因**: 
    1. 币安 API (尤其是 Futures) 对 IP 地区有严格限制，禁止美国、中国大陆等 IP 访问。
    2. `requests` 或 `ccxt` 默认不使用系统代理，导致直接连接失败。
    3. `binanceusdm` 初始化时若尝试连接 Spot API (部分 `load_markets` 实现) 可能会触发额外限制。
- **解决方案**:
    - **代理设置**: 必须显式配置代理。当前使用 Clash 代理 `http://127.0.0.1:33210` (日本节点)。
    - **CCXT 配置**:
        ```python
        options = {
            'defaultType': 'swap',  # 强制使用 Swap (Perpetual) 接口，避免连接 Spot
            'proxies': {
                'http': 'http://127.0.0.1:33210',
                'https': 'http://127.0.0.1:33210'
            }
        }
        ```
    - **API 权限**: 确保 API Key 已开启 "Enable Futures" 权限，且绑定了代理 IP (如需)。

### 1.2 杠杆倍数与持仓模式
- **问题**: 设置杠杆失败 (`Leverage is smaller than permitted`) 或 下单报错 (`Position Side Not Match`)。
- **原因**:
    1. **最小名义价值 (Min Notional)**: 币安合约有最小下单金额限制 (通常 5-100 USDT)。低杠杆下小资金 (如 10U) 无法满足要求。
    2. **持仓模式 (Position Mode)**: 策略默认为单向持仓 (One-Way Mode)，但账户可能设置为双向持仓 (Hedge Mode)。
- **解决方案**:
    - **提高杠杆**: 将杠杆提高至 **20x**，使得 `10 USDT * 20 = 200 USDT` > 最小名义价值。
    - **强制单向模式**: 在代码中检查并设置持仓模式。
        ```python
        # 伪代码
        exchange.fapiPrivatePostPositionSideDual({'dualSidePosition': 'false'})
        ```

### 1.3 监控页面数据异常
- **问题**: 
    - 页面显示虚假/旧的交易记录。
    - 累计收益 (Total PnL) 未扣除手续费。
    - 持仓显示杠杆为 1x，实际为 20x。
- **修复**:
    - **交易过滤**: 增加 `start_time` 或 `24h` 时间窗口过滤，只显示最近相关的交易。
    - **PnL 计算**: `Total PnL = Σ (Realized PnL - Commission)`.
    - **有效杠杆计算**: API 返回的 `leverage` 字段可能不准确 (或仅代表最大允许杠杆)，应使用 `Position Value / Initial Margin` 计算实际生效杠杆。

### 1.4 胜率计算与净收益
- **问题**: 胜率显示错误 (如两单全损显示为 -100% 或其他异常值)。
- **修复**:
    - **胜率逻辑**: `Win Rate = (Winning Trades / Total Trades) * 100%`.
    - **修正记录**: 用户指出两单全损时胜率应为 **0%**。后端已修正计算逻辑，确保分母不为零且分子正确统计净盈利单。
    - **净收益**: 只有当 `Realized PnL` 足以覆盖 `Commission` 时，交易才被视为有效盈利。

### 1.5 模型适应性与重训练 (Model Retraining)
- **问题**: 初始 ML 模型基于现货/低杠杆数据训练，导致在合约实盘中表现不佳 (如出现全损)。
- **原因**: 缺乏合约特有特征 (Funding Rate, OI) 且未针对高波动率优化。
- **修复 (2026-02-08)**:
    - **数据增强**: 采集了过去 **180天** 的期货 OHLCV、资金费率 (Funding Rate) 和持仓量 (Open Interest) 数据 (之前尝试 60 天数据量不足)。
    - **模型迭代**: 重新训练 XGBoost 模型，在更长周期数据上验证了泛化性 (30m 准确率 64% 左右)。
    - **策略优化**: 引入 Heikin Ashi 平滑噪音，并参考 GitHub (TalonSniper) 策略优化了信号逻辑。

### 1.6 动态离场与软止盈 (Dynamic Exit & Soft TP)
- **问题**: 默认硬止盈 (Hard TP) 容易卖飞 (过早离场)，无法吃到大趋势；硬止损 (Hard SL) 缺乏移动保护。
- **修复**:
    - **软止盈 (Soft TP)**: 移除交易所端硬止盈单。改为本地监控，当价格触及止盈线时，若趋势仍强 (信号同向) 则继续持仓，直到信号转弱或反转。
    - **移动止损 (Trailing Stop)**: 增加逻辑，当 **价格移动 > 1% (对应20x杠杆下的20% ROE)** 时自动将止损上移至保本位，当 **价格移动 > 2% (对应20x杠杆下的40% ROE)** 时锁定 1% 利润。
    - **配置**: 该参数已参数化 (trailing_stop_trigger_pct, trailing_stop_lock_pct)，可在配置中调整。


### 1.7 前端体验与数据可视化优化 (Frontend & Data Visualization)
- **问题**: 
    - 图表每次数据刷新都会重置缩放，无法保持用户视角。
    - 默认周期不符合短线交易习惯 (需默认为 10m)。
    - AI 预测面板和策略日志缺少具体的概率 (Probability) 和置信度 (Confidence) 数值。
    - 实盘统计未明确展示手续费支出。
    - 缺少买卖点标记 (Markers) 和币安样式悬停提示 (Tooltip)。
    - 切换时间周期 (Timeframe) 时图表未及时更新。
- **修复**:
    - **图表优化**: 
        - 默认周期设为 **10m**。
        - 优化 `KlineChart.tsx`，分离初始化与数据更新逻辑，添加 `fitContent()` 回退机制，确保刷新数据时保留用户缩放状态。
        - 修复 Lightweight Charts API 兼容性问题：移除不存在的 `createSeriesMarkers`，改为使用 `series.setMarkers`。
        - **时间周期切换**: 增加 `loading` 状态，强制 React 在切换周期时重新渲染组件，解决无变化问题。
        - **买卖点标记 (Markers)**: 修复了标记无法显示的问题。原因在于交易时间戳 (Trade Timestamp) 与 K线时间戳 (Candle Timestamp) 不完全匹配。增加了二分查找逻辑，将交易映射到最近的K线时间上。
        - **悬停提示 (Tooltip)**: 实现了仿币安样式的悬停提示，使用 `subscribeCrosshairMove` 监听鼠标移动，动态显示 OHLC 和涨跌幅信息。
    - **数据补全**:
        - **AI 面板**: 增加预测概率 (如 75.4%) 和置信度 (Confidence Score) 显示。
        - **策略日志**: 列表增加 `Prob.` 和 `Conf.` 列，并将默认显示数量调整为 **7条**。
        - **未执行原因 (Non-execution Reasons)**: 在 Strategy Signals 面板增加了 "Note" 列，显示策略未执行实盘操作的具体原因 (如 "ML置信度不足", "趋势不符" 等)，解决了用户对 "有信号无交易" 的困惑。
        - **策略信号详情 (Strategy Details)**: 在 Strategy Signals 列表中新增了 **RSI**, **MACD**, **EMA** (Trend) 列，直观展示 TrendMLStrategy 的完整决策逻辑 (Trend + Momentum + ML)。
    - **费用统计**: 后端 `RealTrader` 增加 `total_fees` 计算，前端 Monitor 面板新增 Fees 显示。

### 1.8 系统性能优化 (System Performance Optimization)
- **问题**:
    - 前端图表加载缓慢，API 请求串行执行导致等待时间过长。
    - 后端频繁请求币安 API，可能触发限频或因网络延迟导致响应慢。
    - 实盘连接不稳定，偶发连接重置错误。
- **修复**:
    - **前端并发请求**: 优化 `page.tsx` 中的 `fetchData` 逻辑，使用 `Promise.all` 并行请求 Ticker、History 和 Prediction 接口，显著减少页面加载时间。
    - **后端数据缓存**: 在 `CryptoDataCollector` 和 `FuturesDataCollector` 中实现内存缓存机制。
        - **Current Price**: 缓存 2秒，应对高频轮询。
        - **OHLCV**: 缓存 5秒，避免重复获取 K 线数据。
        - **Funding/OI**: 缓存 60秒，降低对重量级数据的请求频率。
    - **连接稳定性**: 
        - 修复 `RealTrader` 初始化逻辑，禁用 `fetchCurrencies` 选项，避免 CCXT 尝试访问受限的 Spot API (`sapi`) 端点。
        - 确保 `binanceusdm` 仅使用 `fapi` (Futures API) 接口，配合 Clash 代理实现稳定连接。

### 1.9 交易频次优化 (High Frequency Scalping Mode)
- **问题**: 原策略依赖 EMA200 + 30m ML模型，条件过于严苛，导致交易频次极低 (数天一次)，资金利用率不足。
- **优化**: 引入 **高频头皮模式 (Scalping Mode)** 作为补充信号。
    - **逻辑**: 当主趋势信号 (EMA200) 未触发时，检查短线机会。
    - **做多条件**: HA价格 > EMA50 (中短期趋势向上) + ML 10m模型置信度 > 0.7 + 成交量 > 20日均量 + RSI < 75。
    - **做空条件**: HA价格 < EMA50 (中短期趋势向下) + ML 10m模型置信度 < 0.3 + 成交量 > 20日均量 + RSI > 25。
    - **优势**: 利用 10m 模型的灵敏度和 EMA50 的趋势跟随，在保证胜率 (ML高置信度 + 量能确认) 的前提下显著提高开单频次。

### 1.10 连接稳定性与算法订单 (Connection & Algo Orders)
- **问题**: 
    - 后端服务运行正常，但 Trader 组件报错 `Connection refused` 或无法连接 Binance API。
    - 止盈止损 (SL/TP) 订单在 API (`fetchOpenOrders`) 中不可见，导致系统误判无保护单。
- **修复**:
    - **代理增强**: 确认 `uvicorn` 进程启动时可能未正确继承环境变量。在 `RealTrader` 初始化时强制检查并应用 `trader_config.json` 中的 `proxy_url`。
    - **算法订单接口**: 币安合约的 SL/TP 属于 "Algo Orders"。修改 `get_positions` 逻辑，增加调用 `fapiPrivateGetOpenAlgoOrders` 接口，正确获取并在前端显示止损止盈价格。
    - **订单优化脚本**: 编写 `optimize_orders.py`，用于在系统重启或异常后，自动扫描所有持仓，取消旧订单，并根据当前策略参数 (如 2% SL, 3% TP) 使用 `reduceOnly` 模式重新挂单。

### 1.11 策略自适应与多模式 (Adaptive Multi-Mode)
- **问题**: 单一策略参数无法适应 BTC 的多变行情 (低波动时止损过宽，高波动时仓位过重)。
- **优化**:
    - **波动率分类**: 基于 ATR 和收益率标准差将市场分为 Low (Scalp), Normal (Trend), High (Breakout) 三种模式。
    - **动态参数**:
        - **Low**: 3-5x 杠杆，小仓位，固定 SL/TP。
        - **Normal**: 8-12x 杠杆，中仓位，ATR SL/TP。
        - **High**: 15-20x 杠杆，重仓，宽止损。
    - **每日风控**: 增加单日最大亏损 (2%) 熔断机制。
    - **动态回撤止盈**: 记录持仓最高价 (High Water Mark)，回撤 > 1.5% 立即止盈。

## 2. 系统配置参数 (Configuration)

### 2.1 交易参数
- **Symbol**: `BTC/USDT:USDT` (CCXT 统一格式，指代 USDT 本位永续合约)
- **Leverage**: 动态 10x - 20x (基于 TrendML 策略信心度)
- **Risk Management**:
    - Stop Loss (SL): 硬止损 (2.0 ATR)，配合移动止损。
    - Take Profit (TP): 软止盈 (3.0 ATR)，动态持有。

### 2.2 策略逻辑 (TrendMLStrategy)
- **入场**: 趋势 (EMA200) + 动量 (MACD/RSI) + ML 模型预测 (>0.75 概率) 共振。
- **出场**: 达到止盈/止损位，或出现反向信号。
