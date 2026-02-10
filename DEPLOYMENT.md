# ☁️ Cloud Deployment Guide (Aliyun)

This guide describes how to deploy the local project to the Alibaba Cloud server while ensuring **data and model consistency**, **deployment efficiency** (using mirrors), and **minimal footprint** (strict filtering).

## 📋 Prerequisites

1. **Server Access**:
   - **IP**: `106.15.73.181`
   - **User**: `root`
   - **Security Group**: Ensure inbound rules allow TCP ports `3000` (Frontend) and `8000` (Backend).

2. **Local Environment**:
   - macOS with `expect` installed (usually pre-installed).

## 🚀 One-Click Deployment

We have created an automated script that handles file filtering, synchronization, and service restart using strict exclusions and domestic mirrors.

### Steps:

1. **Run Deployment Script**:
   Execute the following command in the project root:
   ```bash
   expect scripts/deploy_with_pass.exp
   ```

### What does the script do?

1. **Environment Prep**:
   - Installs `rsync` on the remote server if missing (using Aliyun/system mirrors).
   - Configures Docker daemon on remote server to use Aliyun Registry Mirror (`registry.cn-hangzhou.aliyuncs.com`) for faster image pulls.

2. **Strict File Sync**:
   - **Uploads**: Core source code, `src/models/saved_models/` (trained models), `src/data/` (datasets), `configs/`.
   - **Excludes**: Development junk (`node_modules`, `.git`, `.vscode`, `tests`, `tmp`, `logs`, `.DS_Store`, `venv`, etc.) to keep deployment clean.
   - **Consistency**: Overwrites server data with local data to ensure "What you see locally is what you get on server".

3. **Optimized Build**:
   - **Backend**: Uses `mirrors.aliyun.com` for Debian apt sources and PyPI packages.
   - **Frontend**: Uses `registry.npmmirror.com` for npm packages.
   - **Docker**: Uses Aliyun registry mirror for base images.

4. **Verification**:
   - Automatically checks if services are responding locally on the server after startup.

## 🛠 Manual Deployment (Reference)

If the automation fails, you can manually replicate the steps:

1. **Sync Files (Strict)**:
   ```bash
   rsync -avz \
       --exclude .git --exclude .vscode --exclude __pycache__ \
       --exclude node_modules --exclude .next --exclude .DS_Store \
       --exclude venv --exclude .env --exclude tests --exclude tmp \
       --exclude "*.log" --exclude docs \
       ./ root@106.15.73.181:/root/binance-tool
   ```

2. **SSH & Deploy**:
   ```bash
   ssh root@106.15.73.181
   cd /root/binance-tool
   
   # Configure Docker Mirror (Optional but recommended)
   # echo '{"registry-mirrors": ["https://registry.cn-hangzhou.aliyuncs.com"]}' > /etc/docker/daemon.json
   # systemctl restart docker

   docker compose down --remove-orphans
   docker compose up -d --build
   docker image prune -f
   ```

## ⚠️ Important Notes

- **Data Overwrite**: The deployment **forcefully aligns** the server's data with your local data. If the server has collected unique live data, **BACK IT UP** before deploying.
- **Security Group**: If you cannot access `http://106.15.73.181:3000` externally, check the Aliyun ECS Security Group settings.
- **Feishu Webhook**: The script creates a default `.env` if missing. Update `FEISHU_WEBHOOK_URL` manually on the server if needed:
  ```bash
  vim /root/binance-tool/.env
  ```
