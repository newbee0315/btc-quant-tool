# 后台自动运行监测程序列表

本文档列出了系统中所有正在运行的后台监测任务、定时任务以及自动分析机器人。

## 1. 核心定时任务 (Scheduler)
由 `src/api/main.py` 中的 `AsyncIOScheduler` 管理，随后端 API 服务启动。

| 任务名称 | 触发时间/频率 | 功能描述 | 对应代码 |
| :--- | :--- | :--- | :--- |
| **实盘交易监控日报** | 每30分钟 (xx:00, xx:30) | 向飞书发送账户权益、持仓盈亏、胜率等核心数据统计。 | `send_hourly_monitor_report` |
| **实时行情广播** | 每 10 秒 | 获取最新 K 线数据，生成 AI 预测信号，并通过 WebSocket 推送给前端页面。 | `broadcast_market_data` |
| **每日数据更新** | 每天 00:00 AM | 调用 `DailyUpdateManager` (或手动运行 `scripts/daily_update.sh`)，增量更新 14 个核心币种的 1m K线数据。 | `daily_update_task` |
| **模型定期重训** | 数据更新后自动触发 | 若每日更新中有新数据入库，自动触发 `train_multicoin.py` 进行全量模型重训 (XGBoost)。同时执行策略优化分析。 | `DailyUpdateManager.run` |
| **权益曲线记录** | 每 1 小时 | 记录当前账户总权益，用于绘制历史收益曲线。 | `paper_trader.record_equity` |
| **策略自动优化机器人** | 每 12 小时 | 分析历史订单表现（胜率、盈亏），自动动态调整交易参数（如 ML 阈值、风控比例）。 | `run_strategy_optimization` |
| **模型自动进化系统** | **持续运行** | 调用 `scripts/auto_optimizer.py`，后台持续训练并优化 14 个目标币种的 XGBoost 模型。当模型达标（准确率>55%, 精确率>52%）时自动热更新替换旧模型。全员达标后自动进入低功耗轮询模式。 | `AutoOptimizer` |
| **服务守护 (Watchdog)** | 每 5 分钟 | 巡检关键调度任务是否存在，检测多币种机器人心跳（multicoin_bot.log 5 分钟内更新），如异常则自动拉起。 | `services_watchdog` |

## 2. 实盘交易机器人 (Trading Bot)
由独立进程 `scripts/run_multicoin_bot.py` 运行，负责具体的下单执行。

*   **运行状态**: 🟢 运行中 (后台进程)
*   **监控范围**: Top 14 核心币种 (BTC, ETH, SOL, BNB, DOGE, XRP, PEPE, AVAX, LINK, ADA, TRX, LDO, BCH, OP)
*   **启动机制**: 顺序初始化（每秒 1 个币种）以避免触发币安 API 频率限制 (429)。
*   **核心功能**:
    *   实时监听 K 线数据
    *   根据 `TrendMLStrategy` 策略生成买卖信号
    *   执行开仓、平仓、止损、止盈
    *   异常订单修复（启动时）
*   **日志**: 已启用滚动日志 `multicoin_bot.log`（10MB × 5），支持长期运行。

## 3. 策略自动优化逻辑 (Analysis Robot)
即上述定时任务中的 **策略自动优化机器人**，其具体逻辑位于 `src/utils/strategy_optimizer.py`。

*   **运行频率**: 每 12 小时自动执行一次
*   **分析对象**: 历史已平仓订单统计数据
*   **优化规则**:
    1.  **低胜率保护**: 若交易次数 > 10 且 胜率 < 30%，自动**提高** ML 预测置信度阈值 (0.65 -> 0.85)，减少出手频率，求稳。
    2.  **高胜率增强**: 若交易次数 > 5 且 胜率 > 60%，自动**降低** ML 预测置信度阈值 (0.65 -> 0.55)，增加出手频率，扩大收益。
    3.  **回撤风控**: 若总亏损超过 100 USDT，自动**降低**单笔交易风险比例 (Risk Per Trade)，保护本金。

## 4. 服务进程一览

| 服务类型 | 启动命令 | 端口/PID | 说明 |
| :--- | :--- | :--- | :--- |
| **后端 API & 调度器** | `uvicorn src.api.main:app` | Port 8000 | 核心服务，承载 API 接口和上述所有定时任务。 |
| **实盘交易机器人** | `python scripts/run_multicoin_bot.py` | PID (动态) | 独立运行的交易执行单元。 |
| **前端页面** | `npm run dev` | Port 3000 | 数据展示与监控界面。 |
| **手动数据更新** | `bash scripts/daily_update.sh` | CLI | 手动触发每日数据更新与模型重训。 |

## 5. 日志与稳健性
- `api_server.log` 启用滚动日志（10MB × 5），避免长期运行磁盘膨胀。
- Watchdog 以 5 分钟为周期巡检任务与进程心跳；多币种机器人按“日志 5 分钟内有更新”判定为健康。
- 时间同步自愈：检测到 Binance 返回 -1021（Timestamp ahead）或时间偏差相关错误时，主动调用 fetch_time 计算与本地的 timeDifference（毫秒）并写入客户端，随后重试，避免签名请求因时间漂移失败。
