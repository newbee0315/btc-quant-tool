- **原因**:
    1. 事件循环繁忙或瞬时阻塞导致定时任务错过触发窗口 (Misfire)。
    2. Webhook 请求偶发超时或网络抖动导致发送失败。
- **修复**:
    - **调度容错**: 将定时任务的 `misfire_grace_time` 提升至 **7200s (2小时)**，同时开启 `coalesce=True`、`max_instances=3`，确保系统从休眠恢复或短期阻塞后仍能补发且不被前一实例阻塞。
    - **守护补发**: 新增守护作业 `hourly_monitor_guard`（每 5 分钟执行一次）。当最近一次成功发送时间距今超过 **45 分钟** 时，自动补发一次“监控报告”，弥补长时间休眠导致的空窗。
    - **发送重试**: 飞书发送增加 **3 次重试**（间隔 2s），超时提升至 **10s**，显著提升投递成功率。
- **涉及代码**:
    - 后端调度与任务: [src/api/main.py](file:///Users/weihui/Desktop/币安工具/src/api/main.py)
    - 飞书发送逻辑: [src/notification/feishu.py](file:///Users/weihui/Desktop/币安工具/src/notification/feishu.py)
- **验证**:
    - 手动触发 `/api/v1/test_notification` 返回 `{"status":"success"}`。
    - `/api/v1/feishu/status` 成功计数增长，`last_success_timestamp` 更新。
    - 检查作业队列：`hourly_monitor` 下一次在整点/半点，`hourly_monitor_guard` 每 5 分钟触发一次。

### 1.14 时间戳偏差导致 API 签名失败 (-1021 Timestamp Ahead)
- **问题**: 后端状态显示 `Error`，错误为：`{"code": -1021, "msg": "Timestamp for this request was 1000ms ahead of the server's time."}`，导致私有接口调用失败，前端显示“连接错误”。
- **原因**: 本机时间较交易所服务器时间快约 1s，签名校验不通过。
- **修复**:
    - **时间同步**: 实例化交易所后主动调用时间差同步。
    - **时间窗放宽**: 设置 `recvWindow = 10000`，容忍短时钟偏差与网络抖动。
- **涉及代码**:
    - 实盘交易器: [src/trader/real_trader.py](file:///Users/weihui/Desktop/币安工具/src/trader/real_trader.py)
- **验证**:
    - `/api/v1/status` 中 `connection_status` = `Connected`，`connection_error` = `None`。
    - 前端状态数秒内从“连接中/连接错误”恢复为“已连接”。

### 1.15 当前连接错误诊断（binanceusdm GET /fapi/v1/exchangeInfo）
- **问题**: `/api/v1/status` 返回 `connection_status = "Error"`，`connection_error = "binanceusdm GET https://fapi.binance.com/fapi/v1/exchangeInfo"`。
- **可能原因**:
    1. 代理未生效或被节点限流/封禁（451/418/超时）。
    2. `uvicorn` 进程未继承代理环境，后端实际直连被拒。
    3. 币安期货接口临时不可用或本地 DNS 解析异常。
    4. API Key 权限不足或被阈值限制（需要 Enable Futures）。
- **快速定位**:
    - 在同一机器 `curl -x http://127.0.0.1:33210 https://fapi.binance.com/fapi/v1/exchangeInfo`，确认代理通畅。
    - 检查后端日志 `api_server.log` 是否有连续的 `exchangeInfo` 报错与超时。
    - 查看当前配置：`trader_config.json` 中 `proxy_url` 是否为 `http://127.0.0.1:33210`，并确保 Clash 运行正常。
    - 通过 `/api/v1/status` 与 `/api/v1/feishu/status` 同步观察恢复情况。
- **修复方案**:
    - 确认并重启本地代理（更换低延迟海外节点，必要时切换地域）。
    - 确保后端进程加载了 `trader_config.json` 的 `proxy_url`（已在 `RealTrader` 初始化中强制应用）。
    - 如仍异常，重启 `uvicorn` 服务与多币种机器人进程以刷新连接。
    - 避免高频 REST 访问，维持当前已优化的轮询与广播频率，降低 418 风险。
    - 若为账号权限问题，登录管理后台开启 Futures 权限或更换 Key。

### 1.16 更新 Trader 配置时保留代理开关 (Preserve Proxy on Update)
- **背景**: 在更新 Trader 配置（切换 Paper/Real）时，如果未传递 `proxy_url`，后端会将其置空，导致新实例未走代理，进而出现连接错误。
- **方案**: 在后端新增保护开关，默认开启：
    - `TraderConfig.preserve_proxy_on_update = True`
    - 当该开关为 `True` 且请求未提供 `proxy_url`（`None` 或空串），系统自动沿用旧配置中的 `proxy_url`，避免意外丢失代理。
- **涉及代码**:
    - 模型与逻辑：[src/api/main.py](file:///Users/weihui/Desktop/币安工具/src/api/main.py)
        - `TraderConfig` 新增 `preserve_proxy_on_update: bool = True`
        - `update_trader_config` 在保存前注入逻辑：若开关启用且新配置未提供 `proxy_url`，则继承旧值。
- **使用说明**:
    - 如果确需显式清空代理，请在请求中传入 `"proxy_url": ""` 且将 `"preserve_proxy_on_update": false`。
    - 查询当前配置：`GET /api/v1/config/trader`（敏感信息已脱敏）
- **验证**:
    - 第一步：通过代理访问 `https://fapi.binance.com/fapi/v1/exchangeInfo` 返回 `200`。
    - 第二步：`POST /api/v1/config/trader` 仅传 `{"mode":"real"}`，随后 `GET /api/v1/config/trader` 仍显示 `proxy_url` 为旧值。
    - 第三步：`/api/v1/status` 的 `connection_status` 为 `Connected`。

### 1.17 前端持仓信息不显示修复 (Watchdog & Status File)
- **问题**: 前端一直显示“连接中”或无持仓信息，且飞书消息未发送。
- **原因**: 
    1. 多币种机器人进程 (`run_multicoin_bot.py`) 未运行，导致 `real_trading_status.json` 未更新。
    2. 后端看门狗 (`services_watchdog`) 检测间隔过长 (30分钟) 且判定条件过严 (1小时无日志更新)，导致未能及时重启机器人。
- **修复**:
    - **缩短检测间隔**: 将看门狗执行间隔从 30 分钟调整为 **5 分钟**。
    - **优化判定逻辑**: 将日志“过期”判定阈值从 1 小时缩短为 **5 分钟**，并增加 `pgrep` 进程检测，确保精准重启。
    - **修复启动路径**: 修正 `subprocess.Popen` 的工作目录和环境，确保脚本能正确加载配置。
- **涉及代码**:
    - 后端服务: [src/api/main.py](file:///Users/weihui/Desktop/币安工具/src/api/main.py)

### 1.18 策略下单仓位过小修复 (Equity Retry)
- **问题**: 策略下单金额远小于预期 (例如 15% 仓位却只开 20U)。
- **原因**: 
    - 获取账户权益 (`get_total_balance`) 时偶发网络错误或 API 限制。
    - 代码在失败时直接回退到默认值 **100.0 USDT**，导致计算出的仓位极小 (15U，触发 20U 最小值)。
- **修复**:
    - **增加重试机制**: 在获取权益失败时，增加 **3 次重试** (间隔 1s)。
    - **优化日志**: 明确记录权益获取失败的警告，并在计算仓位时输出详细的“权益-比例-计划金额”日志，便于排查。
- **涉及代码**:
    - 机器人逻辑: [scripts/run_multicoin_bot.py](file:///Users/weihui/Desktop/币安工具/scripts/run_multicoin_bot.py)
    - 交易核心: [src/trader/real_trader.py](file:///Users/weihui/Desktop/币安工具/src/trader/real_trader.py)

### 1.19 后端 API 连接中断导致前端无数据 (Uvicorn Restart)
- **问题**: 前端一直显示“连接中”或无持仓信息，但后台交易机器人 `run_multicoin_bot.py` 正常运行且 `real_trading_status.json` 持续更新。
- **原因**:
    1. 后端 API 服务 (`uvicorn src.api.main:app`) 进程意外退出或未启动，导致前端无法请求接口。
    2. 看门狗 (`services_watchdog`) 仅检测了定时任务调度和交易机器人，未覆盖 API 服务的存活状态。
- **修复**:
    - **重启服务**: 重新启动 `uvicorn` 服务，恢复 API 接口响应。
    - **增强看门狗**: 在 `src/api/main.py` 的 `services_watchdog` 中增加对 `uvicorn` 进程的检测，若缺失则自动拉起（待实现）。
    - **优化启动脚本**: 完善 `start_services.sh`，确保 API 与 Bot 同时启动。
- **涉及代码**:
    - 后端入口: [src/api/main.py](file:///Users/weihui/Desktop/币安工具/src/api/main.py)
- **验证**:
    - `curl http://127.0.0.1:8000/api/v1/status` 返回 200 OK。
    - 前端页面刷新后立即显示“已连接”。

### 1.20 前端杠杆显示错误与飞书消息优化 (Leverage Display & Feishu Formatting)
- **问题**: 
    1. 前端页面持仓杠杆显示错误（如实际 5x 显示为 1x）。
    2. 飞书监控日报未按收益排序，重点不突出。
- **原因**:
    1. `RealTrader.get_positions` 获取杠杆时优先使用了默认值 `self.leverage`，而未充分利用交易所返回的 `info` 字段中的实际杠杆。
    2. `send_hourly_monitor_report` 遍历持仓时未进行排序和格式化处理。
- **修复**:
    - **杠杆获取优化**: 修改 `src/trader/real_trader.py`，优先从 `pos['info']['leverage']` 获取真实杠杆值。
    - **消息格式化**: 修改 `src/api/main.py`，将持仓按 `unrealized_pnl` 从高到低排序，并对收益数字进行 **加粗** 显示。
    - **立即生效**: 重启后端服务并增加手动触发接口，立即发送更新后的飞书消息。
- **涉及代码**:
    - 交易核心: [src/trader/real_trader.py](file:///Users/weihui/Desktop/币安工具/src/trader/real_trader.py)
    - 监控报告: [src/api/main.py](file:///Users/weihui/Desktop/币安工具/src/api/main.py)
- **验证**:
    - 手动触发 `/api/v1/test-report`，飞书收到按收益排序且加粗的消息。
    - 前端页面持仓杠杆显示正确。

### 1.21 移动止损与激进仓位策略 (Trailing Stop & Aggressive Sizing)
- **问题**: 
    1. 缺乏自动锁利机制（移动止损），在趋势反转时容易回吐利润。
    2. 20U 极小仓位无法满足 10000U 年度目标。
- **原因**:
    1. `RealTrader` 中虽然有 `manage_position` 骨架但未在 `run_multicoin_bot.py` 主循环中调用。
    2. 原有 `risk_per_trade` 设置过低 (2%) 且受限于最小下单金额。
- **修复**:
    1. **移动止损集成**: 在 `scripts/run_multicoin_bot.py` 主循环中增加对现有持仓的 `trader.manage_position` 调用，实现 1% 触发保本损、2% 触发利润锁定。
    2. **仓位调整**: 修改 `config/strategy_config.json`，将 `risk_per_trade` 提升至 **0.35 (35%)**，采用固定比例复利模式。
    3. **策略微调**: 更新 `strategy_explanation.md`，明确激进增长模式下的风险控制（依靠硬止损和移动止损）。
- **涉及代码**:
    - 主程序: [scripts/run_multicoin_bot.py](file:///Users/weihui/Desktop/币安工具/scripts/run_multicoin_bot.py)
    - 交易核心: [src/trader/real_trader.py](file:///Users/weihui/Desktop/币安工具/src/trader/real_trader.py)
    - 配置文件: [config/strategy_config.json](file:///Users/weihui/Desktop/币安工具/config/strategy_config.json)

### 1.22 飞书消息富文本支持 (Interactive Card Markdown)
- **问题**: 飞书普通文本消息 (`text` 类型) 不支持 Markdown 语法 (`**bold**`)，导致监控日报中的加粗标记失效，显示为原始字符。
- **原因**: 飞书 `send_text` 接口仅支持纯文本，需升级为 `interactive` (卡片消息) 或 `post` (富文本) 类型才能支持 Markdown 渲染。
- **修复**:
    - **升级发送接口**: 在 `src/notification/feishu.py` 中新增 `send_markdown` 方法，封装飞书交互式卡片 (`interactive`) 结构。
    - **启用 Markdown**: 使用 `lark_md` 标签包裹消息内容，支持加粗、链接等富文本格式。
    - **调整日报发送**: 修改 `src/api/main.py` 调用新接口发送监控日报，并优化标题显示。
- **涉及代码**:
    - 飞书适配器: [src/notification/feishu.py](file:///Users/weihui/Desktop/币安工具/src/notification/feishu.py)
    - 监控逻辑: [src/api/main.py](file:///Users/weihui/Desktop/币安工具/src/api/main.py)
- **验证**:
    - `/api/v1/test-report` 发送的消息正确渲染加粗的 PnL 数值。

### 1.23 仓位杠杆计算修复与飞书格式精简 (Leveraged Sizing & Feishu Format)
- **问题**: 
    1. 仓位大小仍偏小 (~93U)，未达到激进增长预期的 ~465U，原因是计算名义价值时未乘杠杆倍数。
    2. 飞书消息中 ROI 也被加粗，用户认为格式混乱，要求仅加粗“未实现盈亏”。
- **原因**:
    1. `run_multicoin_bot.py` 原逻辑为 `total_equity * position_pct`，这是本金占用模式，未体现全仓杠杆放大。
    2. `src/api/main.py` 中 Markdown 格式包含了 ROI 的加粗。
- **修复**:
    - **杠杆放大**: 修改 `scripts/run_multicoin_bot.py`，公式更新为 `planned_notional = total_equity * position_pct * target_leverage`。
        - 示例: 266U * 35% * 5x ≈ 465U 名义价值。
    - **格式精简**: 修改 `src/api/main.py`，仅对 `pnl` 数值应用 `**` 加粗，移除 ROI 的加粗和颜色标签。
- **涉及代码**:
    - 机器人逻辑: [scripts/run_multicoin_bot.py](file:///Users/weihui/Desktop/币安工具/scripts/run_multicoin_bot.py)
    - 监控报告: [src/api/main.py](file:///Users/weihui/Desktop/币安工具/src/api/main.py)
- **验证**:
    - 重启 `run_multicoin_bot.py` 后日志显示 "Position Sizing ... Planned=$465.50"。
    - 手动触发 `/api/v1/test-report`，飞书消息仅 PnL 数值加粗。

### 1.24 重置所有旧条件单并执行新策略 (Reset Old Orders for New Strategy)
- **原因**:
    - 用户确认当前盈亏比可行，要求撤销历史旧委托，按新策略（2%止损/6%止盈）执行。
- **修复**:
    - **脚本重写**: 重写 `scripts/cancel_all_orders.py`，针对 14 个监控币种撤销所有挂单。
    - **智能重置**: 增加 `reset_orders` 函数，自动识别当前持仓，并按新策略参数（SL 2%, TP 6%）重新挂出 `STOP_MARKET` 和 `TAKE_PROFIT_MARKET` 订单。
    - **安全机制**: 使用 `reduceOnly=True` 确保止盈止损不反向开仓。
- **涉及代码**:
    - [scripts/cancel_all_orders.py](file:///Users/weihui/Desktop/币安工具/scripts/cancel_all_orders.py)
- **验证**:
    - 脚本运行成功，日志显示 "Reset complete"。
    - 3 个持仓（TRX, ETH, XRP）的止盈止损单已重置。

### 1.25 飞书消息盈亏颜色优化 (Feishu PnL Color Formatting)
- **原因**:
    - 用户要求飞书消息中每个仓位的未实现盈亏按颜色区分：正数用红色加粗，负数用蓝色加粗，以提高辨识度。
- **修复**:
    - **Markdown 渲染**: 修改 `src/api/main.py` 中的 `send_hourly_monitor_report` 函数。
    - **条件格式**: 使用 `<font color='red'>` 和 `<font color='blue'>` 标签对 PnL 数值进行条件渲染。
- **涉及代码**:
    - [src/api/main.py](file:///Users/weihui/Desktop/币安工具/src/api/main.py)
- **验证**:
    - 触发测试报告，确认正收益显示红色，负收益显示蓝色。

## 2. 系统配置参数 (Configuration)

### 2.1 交易参数
- **Symbol**: `BTC/USDT:USDT` (CCXT 统一格式，指代 USDT 本位永续合约)
- **Leverage**: 基础 5x (最大 10x)
- **Position Sizing**: 固定比例 35% (Aggressive Growth for 10000U Target)
- **Risk Management**:
    - Stop Loss (SL): 硬止损 (2.0 ATR) + 移动止损 (Trailing Stop)。
    - Take Profit (TP): 软止盈 (3.0 ATR) + 动态回撤止盈 (Retracement)。

### 2.2 策略逻辑 (TrendMLStrategy)
- **入场**: 趋势 (EMA200) + 动量 (MACD/RSI) + ML 模型预测 (>0.75 概率) 共振。
- **出场**: 达到止盈/止损位，或出现反向信号。
