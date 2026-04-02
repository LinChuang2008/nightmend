# 🚀 Quick Start: Deploy NightMend in 5 Minutes

**Category: Q&A**

---

Get NightMend running locally with Docker Compose in under 5 minutes.

## Prerequisites

- Docker 20.10+
- Docker Compose v2+
- 2GB+ free RAM

## Step-by-Step

### 1. Clone the repo

```bash
git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — set your DeepSeek API key for AI features (optional)
```

### 3. Start everything

```bash
docker compose up -d
```

This launches 4 containers:
| Container | Port | Purpose |
|-----------|------|---------|
| frontend | 3001 | React dashboard |
| backend | 8001 | FastAPI API server |
| postgres | 5432 | PostgreSQL database |
| redis | 6379 | Cache & pub/sub |

### 4. Access the dashboard

Open http://localhost:3001 — default login is in your `.env` file.

### 5. Add your first host

Navigate to **Hosts → Add Host**, or deploy the NightMend Agent:

```bash
# On the target server
curl -sSL https://raw.githubusercontent.com/LinChuang2008/nightmend/main/scripts/install-agent.sh | bash
```

## Common Issues

### Q: Port 3001/8001 already in use?
Edit `docker-compose.yml` and change the host port mapping.

### Q: AI features not working?
Make sure `DEEPSEEK_API_KEY` is set in `.env`. AI features are optional — everything else works without it.

### Q: Database connection errors on startup?
Wait 10-15 seconds for PostgreSQL to initialize, then restart the backend:
```bash
docker compose restart backend
```

### Q: How to check logs?
```bash
docker compose logs -f backend   # API logs
docker compose logs -f frontend  # Frontend build logs
```

---

## 🇨🇳 中文版

### 5 分钟部署 NightMend

#### 前置条件
- Docker 20.10+
- Docker Compose v2+
- 2GB+ 可用内存

#### 部署步骤

```bash
# 1. 克隆仓库
git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，设置 DeepSeek API Key（可选，AI 功能需要）

# 3. 一键启动
docker compose up -d

# 4. 访问 http://localhost:3001
```

#### 常见问题

- **端口冲突？** 修改 `docker-compose.yml` 中的端口映射
- **AI 功能不工作？** 检查 `.env` 中的 `DEEPSEEK_API_KEY`
- **数据库连接错误？** 等待 15 秒后重启 backend：`docker compose restart backend`

有其他问题？在这个帖子下方回复！
