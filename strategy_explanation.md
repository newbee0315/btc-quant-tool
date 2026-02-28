# 策略说明文档 (Strategy Explanation)

## 核心逻辑 (Core Logic)

本策略是一个基于 **多模型投票集成 (Ensemble ML)** 与 **市场状态自适应 (Regime Adaptive)** 相结合的 **多币种趋势跟踪与高频均值回归策略**。
旨在通过机器学习模型预测短期价格涨跌概率，结合深度订单流数据 (Order Flow) 和市场状态分类，实现全天候自动化交易。

---

### 1. 信号生成机制 (Signal Generation)

策略信号由 **ML 集成模型**、**市场状态分类器** 和 **技术/资金指标** 三层漏斗决定：

#### A. 机器学习集成 (Ensemble ML) - [UPDATED]
- **多模型架构**:
  - **XGBoost**: 捕捉非线性关系，作为主模型。
  - **LightGBM**: 高效处理大量特征，提供辅助投票。
  - **Random Forest**: 降低过拟合风险，提供稳定性。
- **软投票机制 (Soft Voting)**:
  - 综合各模型的预测概率，取平均值作为最终 `ML_Prob`。
  - **多时间窗口**: 同时预测 10m 和 30m 两个时间视窗，要求方向共振。
- **预测目标**: 未来 10-30 分钟的收益率方向 (Class 1: Up, Class 0: Down)。
- **输入特征 (Features)**:
  - **基础**: OHLCV, Lagged Returns.
  - **技术**: RSI, MACD, ATR, Bollinger, EMA, ADX.
  - **高级**: **Taker Buy/Sell Ratio** (主动买卖流), **F&G Index** (情绪).

#### B. 市场状态自适应 (Market Regime Adaptation) - [NEW]
通过 `MarketRegimeClassifier` 自动识别当前市场环境，动态调整策略参数：
- **Trending (趋势模式)**: ADX > 25。
  - **策略**: 趋势跟踪。
  - **参数**: 宽止损 (2%)，宽止盈 (6%)，ML 阈值 0.60。
- **Ranging (震荡模式)**: ADX < 20 & Low Volatility。
  - **策略**: **高频剥头皮 (Scalping)**。
  - **参数**: 紧止损 (1%)，紧止盈 (1.5%)，ML 阈值 0.55。
  - **入场**: 依赖 **OBI (订单簿不平衡)** 和 **Taker Flow** 确认。
- **Volatile (高波模式)**: ATR Percentile > 80%。
  - **策略**: 降低仓位，提高杠杆（捕捉爆发）。
  - **参数**: 仓位减半，杠杆最高 **10x** (严格限制)。

#### C. 高频因子增强 (High Frequency Factors) - [NEW]
仅在 **Scalping Mode** 下激活，用于微观择时：
- **OBI (Order Book Imbalance)**: `(BidQty - AskQty) / (BidQty + AskQty)` > 0.1 (看多)。
- **Taker Flow**: 主动买入量 > 主动卖出量 (Ratio > 1.05)。

#### D. 最终信号 (Final Signal)
- **LONG**: 
  - `Ensemble_Prob > Threshold` (0.60/0.55)
  - `Market_Regime` 匹配
  - `RSI < 80` (Trend) 或 `RSI < 70` (Scalp)
  - `Price > EMA200` (Trend) 或 `Price > EMA50` (Scalp)
  - **动量确认**: `Price > EMA20` (防止接飞刀) - [NEW]
  - **反转特例**: 若 `Price` 强势突破 `EMA50` 且 `ML > 0.75`，可忽略 EMA200 限制 (Breakout Reversal)。
  - `OBI > 0.1` (仅 Scalp)

- **SHORT**:
  - `Ensemble_Prob < Threshold`
  - `RSI > 20` (Trend) 或 `RSI > 30` (Scalp)
  - `Price < EMA200` (Trend) 或 `Price < EMA50` (Scalp)
  - **动量确认**: `Price < EMA20` (防止追空被套) - [NEW]
  - **反转特例**: 若 `Price` 强势跌破 `EMA50` 且 `ML < 0.25`，可忽略 EMA200 限制 (Breakout Reversal)。
  - `OBI < -0.1` (仅 Scalp)

---

### 2. 资金管理与风控 (Risk Management)

#### A. 科学仓位管理 (Kelly & Volatility) - [UPDATED]
- **凯利公式 (Half-Kelly)**:
  - 基于 ML 预测胜率 (`p`) 和 赔率 (`b` = TP/SL) 动态计算最佳仓位比例。
  - 公式: `f = 0.5 * (p(b+1) - 1) / b`。
  - 目的: 在胜率高时加大注码，胜率低时减少暴露。
- **波动率调节 (Volatility Scaling)**:
  - 仓位大小与 ATR 成反比。市场波动越剧烈，单笔仓位越小，保持风险恒定。
- **硬性限制**:
  - **单仓上限**: 不超过总购买力 (Equity * Leverage) 的 **30%**。
  - **总杠杆上限**: 全局强制最大 **10x**。基础配置 5x，高确信度 (ML>0.8) 可提升至 8-10x。

#### B. 止盈止损 (Exit Strategy)
- **Trend Mode**: Risk:Reward **1:3** (SL 2%, TP 6%)。
- **Scalp Mode**: Risk:Reward **1:1.5** (SL 1%, TP 1.5%)。
- **动态追踪 (Trailing Stop)**:
  - **触发条件**: 浮动盈利 > 1%。
  - **回撤限制**: 价格从最高点回撤 2% 时离场（或保本损）。
  - **目的**: 在趋势延续时尽可能多吃利润，在趋势反转时保护利润。
- **部分止盈 (Partial TP)**:
  - **触发条件**: 浮动盈利达到 3% 时。
  - **执行动作**: 自动平仓 50% 仓位。
  - **目的**: 落袋为安，降低心理压力，确保每笔盈利交易都有实际收益。

#### C. 相关性风控 (Correlation Management) - [NEW]
为防止“一损俱损”，引入投资组合相关性检查：
- **机制**: 每次开仓前，计算目标币种与当前持仓币种的收益率相关系数 (Correlation Coefficient)。
- **阈值**: 如果与任一现有持仓的相关性 > **0.65**，则禁止开仓。
- **效果**: 强制分散投资，避免在同向波动的资产上过度暴露风险。

---

### 3. 执行层微操 (Execution Optimization) - [NEW]

#### Smart Entry & Chase (智能进场与追单)
为解决高频交易中的滑点和踏空问题，`RealTrader` 实现了 Phase 4 执行逻辑：
1.  **Maker 优先**: 信号触发时，优先以 **买一/卖一价 (Best Bid/Ask)** 挂限价单 (Limit Order)。
2.  **超时监控**: 监控挂单 **5秒**。
3.  **Taker 追单**: 若 5秒内未完全成交，自动撤单并以 **市价 (Market)** 追单剩余部分。
4.  **效果**: 既能争取 Maker 手续费优惠，又能保证极端行情下的成交率。

---

### 4. 目标与可行性
- **目标**: 365天 10,000 USDT。
- **核心**: 通过 **多策略并行 (Trend + Scalp)** 提高资金周转率，利用 **凯利公式** 优化注码，利用 **Smart Entry** 降低损耗，严格执行 **10x 杠杆封顶**。

---
**Last Updated**: 2026-02-27 (Phase 0-4 Implemented)
