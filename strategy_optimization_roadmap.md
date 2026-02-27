# 策略优化路线图 (Strategy Optimization Roadmap)

**终极目标**: 365天内将账户资金增长至 10,000 USDT。
**核心理念**: 稳健增长（Trend）+ 低波高频（Scalping），严格风控保护本金。

---

## ✅ Phase 0: 基础风控与模式确立 (已完成)

**状态**: 2026.02.27 已上线
**核心变更**:
1.  **动态杠杆上限**:
    *   基础上限: **5x** (适用于绝大多数行情)
    *   高确信度上限: **8x** (仅当 ML预测胜率 > 80% 且 趋势强烈时)
2.  **单仓位限制**:
    *   单个币种最大持仓（名义价值）严格限制为 **总购买力 (权益×杠杆) 的 30%**。
3.  **双模式并行**:
    *   **趋势模式 (Trend Mode)**: 盈亏比 **1:3** (SL 2%, TP 6%)。
    *   **高频模式 (Scalp Mode)**: 低波动率环境下自动激活，SL 1%, TP 1.5%。

---

## 🚀 Phase 1: 数据深度与高频增强 (优先级: 最高)

**状态**: 2026.02.27 代码已实现 (Pending Validation)

**痛点**: 当前高频模式仅依赖 K线 (OHLCV) 和 RSI，数据颗粒度不够，容易滞后。
**优化方案**:
1.  **引入订单簿 (Order Book) 数据**:
    *   监控 **买一/卖一队列深度 (Bid/Ask Depth)**。
    *   计算 **订单簿不平衡指标 (Order Book Imbalance, OBI)**: `(BidQty - AskQty) / (BidQty + AskQty)`。
    *   *作用*: 提前预判微观价格压力方向。
2.  **资金流向监控 (Trade Flow)**:
    *   计算 **主动买入/主动卖出比率 (Taker Buy/Sell Ratio)**。
    *   监控大单成交 (Whale Alert) 作为短线爆发信号。
3.  **升级高频信号逻辑**:
    *   原逻辑: `RSI < 70` + `HA Candle`
    *   新逻辑: `RSI < 70` + `OBI > Threshold` + `TakerBuy > TakerSell`

**预计效果**: 提高震荡行情下的胜率，减少假突破磨损。

---

## ⚖️ Phase 2: 科学资金管理 (优先级: 中)

**状态**: 2026.02.27 代码已实现 (Pending Validation)

**痛点**: 当前 5x/8x 杠杆属于经验值，缺乏数学模型支撑，可能在低赔率机会上过度下注。
**优化方案**:
1.  **引入凯利公式 (Kelly Criterion)**:
    *   利用 ML 模型输出的 **胜率概率 (Probability)** 动态计算仓位。
    *   公式变体: `Position_Size = Leverage * (Probability * (Odds + 1) - 1) / Odds`
    *   *安全修正*: 采用 **半凯利 (Half-Kelly)** 以降低破产风险。
2.  **波动率调节 (Volatility Scaling)**:
    *   仓位大小与 ATR 成反比：波动越大，仓位越小。

**预计效果**: 资金曲线更平滑，大幅降低回撤风险。

---

## 🧠 Phase 3: 模型集成与进化 (优先级: 中)

**状态**: 2026.02.27 基础架构已就绪 (Infrastructure Ready)

**痛点**: 单一 XGBoost 模型容易过拟合，且对不同市场状态适应性差。
**优化方案**:
1.  **多模型投票 (Ensemble)**:
    *   **实现**: `PricePredictor` 已升级支持多模型加载 (XGBoost, LightGBM, Random Forest) 和软投票 (Soft Voting) 机制。
    *   **状态**: 架构已完成，等待模型训练文件。
2.  **市场状态识别器 (Market Regime Classifier)**:
    *   **实现**: 新增 `MarketRegimeClassifier` 模块，基于 ADX (趋势强度)、ATR Percentile (波动率分位) 和 EMA Slope (方向) 自动识别市场状态。
    *   **分类**: `TRENDING` (趋势), `RANGING` (震荡), `VOLATILE` (高波).
    *   **应用**: 已集成至 `TrendMLStrategy`，自动切换 Low/High/Normal 模式。

**预计效果**: 提升在复杂行情下的适应能力，过滤 30%+ 的虚假信号。

---

## ⚡ Phase 4: 执行层微操 (优先级: 低)

**状态**: 2026.02.27 部分实现 (Smart Entry Implemented)

**痛点**: 高频交易中，挂单 (Maker) 容易因 0.01% 的价格波动而无法成交，导致踏空。
**优化方案**:
1.  **队列位置预估 (Queue Position)**:
    *   (暂缓) 估算自己在订单簿中的排队位置。
2.  **智能进场与追单 (Smart Entry & Chase)**:
    *   **已实现**: `_smart_entry` 机制。优先尝试 Limit Order (Best Bid/Ask) 成为 Maker。
    *   **追单**: 监控挂单超时 (5秒)。如果未成交，自动撤单并以 Market Order (Taker) 追单，确保成交。

---

## 📅 下一步行动计划 (Action Plan)

1.  **[验证]** 观察实盘日志中 `Smart Entry` 的触发情况与成交效果。
2.  **[监控]** 关注 `Phase 3` 多模型投票的准确率与 `Market Regime` 的分类稳定性。
3.  **[待办]** (Phase 4) 未来考虑实现队列位置预估 (需 L3 数据)。

## ✅ 已完成 (Completed Actions)
*   **[数据]** `collect_futures_data.py` (Collector) 已集成 Taker Buy/Sell Volume。
*   **[策略]** `TrendMLStrategy` 已实现 OBI 与 Flow 因子逻辑。
*   **[风控]** `PortfolioManager` 已集成凯利公式与波动率调节。
