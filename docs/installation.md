# NightMend 安装指南

> 详细的部署配置文档，涵盖 Docker Compose 部署、手动部署、环境变量、反向代理和升级。

## 目录

- [Docker Compose 部署（推荐）](#docker-compose-部署推荐)
- [环境变量配置](#环境变量配置)
- [手动部署](#手动部署)
- [端口说明](#端口说明)
- [HTTPS 反向代理配置](#https-反向代理配置)
- [升级指南](#升级指南)

---

## Docker Compose 部署（推荐）

### 前置条件

- Docker 20.0+
- Docker Compose v2.0+
- 2 核 4GB 内存以上

### 部署步骤

```bash
git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend
cp .env.example .env
```

编辑 `.env` 文件，**至少修改以下两项**：

```bash
# 必须修改！使用强密码
POSTGRES_PASSWORD=your-strong-password-here

# 必须修改！生成随机密钥
JWT_SECRET_KEY=$(openssl rand -hex 32)
```

启动服务：

```bash
docker compose up -d
```

### docker-compose.yml 参考

项目自带的 `docker-compose.yml` 包含 4 个服务：

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: ${POSTGRES_DB:-nightmend}
      POSTGRES_USER: ${POSTGRES_USER:-nightmend}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-nightmend_dev_password}
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-nightmend}"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  backend:
    build: ./backend
    ports:
      - "8001:8000"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    volumes:
      - ./backend:/app

  frontend:
    build: ./frontend
    ports:
      - "3001:80"
    depends_on:
      - backend

volumes:
  pgdata:
  redisdata:
```

### 验证部署

```bash
# 查看服务状态
docker compose ps

# 检查后端健康状态
curl http://localhost:8001/api/health

# 访问前端
open http://localhost:3001
```

---

## 环境变量配置

将 `.env.example` 复制为 `.env` 后按需修改。以下是完整的环境变量说明：

### 数据库配置

| 变量 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `POSTGRES_HOST` | PostgreSQL 主机地址 | 否 | `postgres`（Docker 内部服务名） |
| `POSTGRES_PORT` | PostgreSQL 端口 | 否 | `5432` |
| `POSTGRES_DB` | 数据库名 | 否 | `nightmend` |
| `POSTGRES_USER` | 数据库用户名 | 否 | `nightmend` |
| `POSTGRES_PASSWORD` | 数据库密码 | **是** | `change-me` |

> ⚠️ 生产环境务必修改 `POSTGRES_PASSWORD`，不要使用默认值。

### Redis 配置

| 变量 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `REDIS_HOST` | Redis 主机地址 | 否 | `redis`（Docker 内部服务名） |
| `REDIS_PORT` | Redis 端口 | 否 | `6379` |

### JWT 认证

| 变量 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `JWT_SECRET_KEY` | JWT 签名密钥 | **是** | `change-me-in-production` |
| `JWT_ALGORITHM` | 签名算法 | 否 | `HS256` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access Token 有效期（分钟） | 否 | `120` |
| `JWT_REFRESH_TOKEN_EXPIRE_DAYS` | Refresh Token 有效期（天） | 否 | `7` |

> ⚠️ 生产环境务必修改 `JWT_SECRET_KEY`：`openssl rand -hex 32`

### AI 配置（可选）

启用 AI 智能分析功能（告警根因分析、日志智能解读等）需要配置：

| 变量 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `AI_PROVIDER` | AI 服务提供商 | 否 | `deepseek` |
| `AI_API_KEY` | API 密钥 | 启用 AI 时必填 | （空） |
| `AI_API_BASE` | API 基础 URL | 否 | `https://api.deepseek.com/v1` |
| `AI_MODEL` | 模型名称 | 否 | `deepseek-chat` |
| `AI_MAX_TOKENS` | 最大输出 Token 数 | 否 | `2000` |
| `AI_AUTO_SCAN` | 自动异常扫描 | 否 | `false` |

### 运维记忆系统（可选）

集成 Engram 服务，为 AI 分析提供历史上下文：

| 变量 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `MEMORY_API_URL` | 记忆服务 API 地址 | 否 | `http://host.docker.internal:8002/api/v1/memory` |
| `MEMORY_ENABLED` | 是否启用记忆功能 | 否 | `true` |

### 自动修复系统（可选）

| 变量 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `AGENT_ENABLED` | 是否启用自动修复 Agent | 否 | `false` |
| `AGENT_DRY_RUN` | 试运行模式（仅记录不执行） | 否 | `true` |
| `AGENT_MAX_AUTO_PER_HOUR` | 每小时最大自动修复次数 | 否 | `10` |

> 💡 建议先以 `AGENT_DRY_RUN=true` 运行一段时间，确认修复动作符合预期后再关闭试运行。

### 后端服务

| 变量 | 说明 | 必填 | 默认值 |
|------|------|:----:|--------|
| `BACKEND_HOST` | 后端监听地址 | 否 | `0.0.0.0` |
| `BACKEND_PORT` | 后端监听端口 | 否 | `8000` |

---

## 手动部署

适用于不使用 Docker 的环境。

### 前置条件

- Python 3.11+
- Node.js 18+
- PostgreSQL 16
- Redis 7

### 后端部署

```bash
cd backend

# 创建虚拟环境
python -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp ../.env.example .env
# 编辑 .env，将 POSTGRES_HOST 和 REDIS_HOST 改为实际地址（如 localhost）

# 初始化数据库（首次运行自动创建表）
python -m uvicorn app.main:app --host 0.0.0.0 --port 8001
```

使用 systemd 管理后端：

```bash
cat > /etc/systemd/system/nightmend-backend.service << 'EOF'
[Unit]
Description=NightMend Backend
After=network.target postgresql.service redis.service

[Service]
Type=simple
User=nightmend
WorkingDirectory=/opt/nightmend/backend
EnvironmentFile=/opt/nightmend/.env
ExecStart=/opt/nightmend/backend/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now nightmend-backend
```

### 前端部署

```bash
cd frontend

# 安装依赖
npm install

# 构建生产版本
npm run build

# 产物在 dist/ 目录，使用 Nginx 托管
```

Nginx 配置示例（托管前端静态文件）：

```nginx
server {
    listen 3001;
    server_name localhost;
    root /opt/nightmend/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

---

## 端口说明

| 服务 | 容器内端口 | 宿主机映射端口 | 协议 | 说明 |
|------|:----------:|:--------------:|:----:|------|
| 前端（Nginx） | 80 | **3001** | HTTP | Web 管理界面 |
| 后端（Uvicorn） | 8000 | **8001** | HTTP/WS | REST API + WebSocket |
| PostgreSQL | 5432 | **5433** | TCP | 数据库 |
| Redis | 6379 | **6380** | TCP | 缓存/消息队列 |

> 💡 如需修改映射端口，直接编辑 `docker-compose.yml` 中的 `ports` 字段。格式为 `宿主机端口:容器端口`。

---

## HTTPS 反向代理配置

生产环境强烈建议使用 HTTPS。以下是 Nginx 反向代理示例：

### 安装 Nginx 和 Certbot

```bash
# Ubuntu/Debian
apt install -y nginx certbot python3-certbot-nginx

# CentOS/RHEL
dnf install -y nginx certbot python3-certbot-nginx
```

### Nginx 配置

```nginx
server {
    listen 80;
    server_name nightmend.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name nightmend.example.com;

    ssl_certificate     /etc/letsencrypt/live/nightmend.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/nightmend.example.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # 前端
    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # 后端 API
    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket
    location /ws/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

### 申请 SSL 证书

```bash
certbot --nginx -d nightmend.example.com
```

### 自动续期

```bash
# Certbot 默认已配置自动续期，验证：
systemctl status certbot.timer
```

---

## 升级指南

### Docker Compose 升级

```bash
cd nightmend

# 拉取最新代码
git pull origin main

# 重新构建并启动（--build 强制重新构建镜像）
docker compose up -d --build

# 查看日志确认启动正常
docker compose logs -f --tail=50
```

> 💡 数据库数据保存在 Docker Volume 中，升级不会丢失数据。

### 手动部署升级

```bash
cd /opt/nightmend

# 拉取最新代码
git pull origin main

# 更新后端依赖
cd backend
source venv/bin/activate
pip install -r requirements.txt

# 重启后端
systemctl restart nightmend-backend

# 重新构建前端
cd ../frontend
npm install
npm run build

# 重启 Nginx（如果前端有变化）
systemctl reload nginx
```

### 数据库迁移

NightMend 在启动时会自动检测并执行数据库迁移。如需手动执行：

```bash
# Docker 环境
docker compose exec backend python -m alembic upgrade head

# 手动环境
cd backend
source venv/bin/activate
alembic upgrade head
```

### 回滚

如果升级后出现问题：

```bash
# 回退到上一个版本
git log --oneline -5   # 查看最近提交
git checkout <commit-hash>

# Docker 重新构建
docker compose up -d --build
```

---

## 常见问题

**Q: 端口被占用怎么办？**

修改 `docker-compose.yml` 中的端口映射，例如将前端改为 8080：

```yaml
frontend:
  ports:
    - "8080:80"
```

**Q: 如何查看后端日志？**

```bash
# Docker 环境
docker compose logs -f backend

# 手动部署
journalctl -u nightmend-backend -f
```

**Q: 如何备份数据？**

```bash
# 备份 PostgreSQL
docker compose exec postgres pg_dump -U nightmend nightmend > backup_$(date +%Y%m%d).sql

# 恢复
cat backup_20260221.sql | docker compose exec -T postgres psql -U nightmend nightmend
```
