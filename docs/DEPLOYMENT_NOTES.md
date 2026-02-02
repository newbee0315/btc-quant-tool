# 阿里云服务器部署实战记录 & 避坑指南

> **部署时间**: 2026-02-01 (Updated)
> **服务器**: 阿里云轻量应用服务器 (IP: 106.15.73.181)  
> **项目**: 币安量化分析工具 (Next.js + FastAPI + Docker)

本文档详细记录了将本项目部署到阿里云服务器的全过程，重点总结了遇到的技术陷阱（Pitfalls）及其解决方案，供后续维护参考。

---

## 1. 核心操作步骤 (Deployment Steps)

### 1.1 一键更新部署 (Recommended)
我们已创建自动化脚本来打包、上传并部署更新。

1. **本地执行**:
   ```bash
   # 1. 创建部署包 (排除 node_modules 等大文件)
   tar --exclude='frontend/node_modules' --exclude='frontend/.next' --exclude='__pycache__' --exclude='.git' -czf project_update.tar.gz frontend src scripts docker-compose.yml Dockerfile.frontend Dockerfile.backend requirements.txt .dockerignore

   # 2. 运行自动部署脚本
   expect deploy_update.exp
   ```

### 1.2 手动环境初始化与代码上传 (Legacy)
- **自动化上传**: 使用 `expect` 脚本封装 `scp` 命令，自动处理 SSH 密码输入，避免手动交互繁琐。
- **目录结构**: 项目部署在 `/root/binance-tool`。

### 1.2 Docker 环境配置
- **镜像源优化**: 
  - 后端 (`Dockerfile.backend`): 替换 `deb.debian.org` 为 `mirrors.aliyun.com`，pip 源使用阿里云镜像，显著提升构建速度。
  - 前端 (`Dockerfile.frontend`): 升级 Node.js 至 v20 以兼容 Next.js 14+。

### 1.3 服务启动与编排
- **Docker Compose**: 使用 `docker compose up -d --build` 启动服务。
- **数据持久化**: 
  - 模型文件挂载: `./src/models/saved_models:/app/src/models/saved_models`
  - 交易状态挂载: `./paper_trading_state.json:/app/paper_trading_state.json`

---

## 2. 踩坑与解决方案 (Troubleshooting & Pitfalls)

### 🛑 1. 内存溢出 (OOM) 导致训练进程被杀
- **现象**: 在服务器执行 `train.py` 时，进程运行一段时间后突然终止，无报错信息（被系统 OOM Killer 杀掉）。
- **原因**: 原代码使用 `RandomizedSearchCV` 进行超参数网格搜索，且 XGBoost 默认尝试使用多核并行，导致 2GB/4GB 内存瞬间耗尽。
- **解决方案**: 
  - 修改 [train.py](src/models/train.py)，移除 `RandomizedSearchCV`。
  - 使用固定的、经验证的高性能参数组合。
  - **关键设置**: 强制设置 `n_jobs=1`，限制 XGBoost 仅使用单线程，降低内存峰值。

### 🛑 2. Docker 挂载文件自动变成“目录”
- **现象**: 后端报错 `IsADirectoryError: .../paper_trading_state.json`。
- **原因**: Docker 启动时，如果挂载的宿主机文件**不存在**，Docker 守护进程会自动创建一个同名的**目录**而不是文件。
- **解决方案**: 
  - 在 `docker compose up` 之前，必须手动在服务器上创建该文件：`touch paper_trading_state.json && echo "{}" > paper_trading_state.json`。

### 🛑 3. 前端页面白屏与接口连接失败
- **现象**: 部署后访问前端页面，UI 加载出来了，但数据全空，或者直接白屏报错。
- **原因 1 (接口地址)**: 前端构建时 `NEXT_PUBLIC_API_URL` 默认为 `localhost`。用户浏览器访问时，`localhost` 指向的是用户自己的电脑，而非阿里云服务器。
- **原因 2 (字段缺失)**: 后端生成的 `model_metrics.json` 缺少 `sample_size`, `training_date` 等字段，导致前端 `page.tsx` 解析时抛出 `undefined` 异常。
- **解决方案**:
  - 前端：确保环境变量或代码逻辑能动态识别服务器 IP（或在构建时注入正确 IP）。
  - 后端：同步前后端数据契约，修改 `train.py` 确保输出字段与前端接口定义 (`interface ModelMetric`) 完全一致。

### 🛑 4. 构建过程“卡死” (Terminal Stuck)
- **现象**: 执行 `docker compose build` 时，终端在 `Running npm install` 或 `pip install` 处长时间不动。
- **原因**: 
  - 服务器带宽或 CPU 限制。
  - npm/pip 默认源在海外，连接超时。
- **解决方案**: 
  - **换源**: 强制在 Dockerfile 中写入阿里云/清华镜像源。
  - **耐心**: 前端 Next.js 编译在低配服务器上可能需要 5-10 分钟，并非真的死机。

### 🛑 5. 依赖缺失
- **现象**: 后端报错 `ModuleNotFoundError: No module named 'matplotlib'`。
- **原因**: 本地开发环境已安装但未更新到 `requirements.txt`。
- **解决方案**: 更新 `requirements.txt`，添加 `matplotlib`, `apscheduler`, `xgboost` 等核心依赖。

---

## 3. 常用维护命令 (Cheatsheet)

### 重新部署后端 (代码修改后)
```bash
# 1. 上传修改后的文件 (在本地执行)
scp src/models/train.py root@106.15.73.181:/root/binance-tool/src/models/

# 2. 重建并重启后端 (在服务器执行)
docker compose up -d --build backend
```

### 手动触发模型训练
```bash
docker compose exec backend python src/models/train.py
```

### 查看实时日志
```bash
# 查看最后 100 行并持续跟踪
docker compose logs -f --tail=100 backend
```

### 检查服务状态
```bash
docker compose ps
```
