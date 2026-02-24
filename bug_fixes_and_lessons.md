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
