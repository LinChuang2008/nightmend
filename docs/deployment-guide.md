# NightMend Deployment Guide / 部署指南

## System Requirements / 系统要求

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | CentOS 7+, Ubuntu 20.04+, Debian 11+ | Ubuntu 22.04 LTS |
| CPU | 2 cores | 4+ cores |
| RAM | 2 GB | 4+ GB |
| Disk | 10 GB | 20+ GB SSD |
| Docker | 20.10+ | Latest |
| Docker Compose | v2.0+ | Latest |

## Quick Start / 快速开始

```bash
# Clone & install / 克隆并安装
git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend
./install.sh
```

That's it! The interactive wizard will guide you through configuration.

就这么简单！交互式向导会引导你完成配置。

## Detailed Configuration / 详细配置

### Environment Variables / 环境变量

The installer generates `.env` automatically. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_PASSWORD` | (random) | Database password / 数据库密码 |
| `JWT_SECRET_KEY` | (random) | JWT signing key / JWT 签名密钥 |
| `AI_API_KEY` | (empty) | DeepSeek API key for AI features / AI 功能密钥 |
| `AI_API_BASE` | `https://api.deepseek.com/v1` | AI API endpoint |
| `AI_MODEL` | `deepseek-chat` | AI model name |

### Port Configuration / 端口配置

| Service | Default Port | Env Override |
|---------|-------------|--------------|
| Frontend | 3001 | Interactive prompt |
| Backend API | 8001 | Interactive prompt |
| PostgreSQL | 5433 | Interactive prompt |
| Redis | 6380 | Interactive prompt |

Ports are stored in `docker-compose.override.yml`.

### AI Features / AI 功能

AI analysis is optional. To enable:
1. Get a DeepSeek API key from https://platform.deepseek.com
2. Enter it during installation, or edit `.env` later:
   ```
   AI_API_KEY=sk-your-key-here
   ```
3. Restart: `docker compose restart backend`

## Agent Installation / Agent 安装

The NightMend Agent runs on monitored servers to collect metrics and logs.

### Install Agent / 安装 Agent

```bash
# On each monitored server / 在每台被监控服务器上
pip install nightmend-agent  # (coming soon)

# Or run directly / 或直接运行
cd nightmend/agent
pip install -r requirements.txt
python -m nightmend_agent \
  --server http://YOUR_NIGHTMEND_SERVER:8001 \
  --token YOUR_AGENT_TOKEN
```

### Get Agent Token / 获取 Agent Token

1. Log in to NightMend dashboard
2. Go to Settings → Agent Tokens
3. Create a new token
4. Use it in the agent configuration

### Systemd Service / 系统服务

```bash
cat > /etc/systemd/system/nightmend-agent.service <<EOF
[Unit]
Description=NightMend Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/nightmend-agent --server http://YOUR_SERVER:8001 --token YOUR_TOKEN
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl enable --now nightmend-agent
```

## Management Commands / 管理命令

```bash
# View logs / 查看日志
docker compose logs -f
docker compose logs -f backend    # Backend only

# Restart services / 重启服务
docker compose restart

# Stop / 停止
docker compose down

# Uninstall (interactive) / 卸载
./install.sh --uninstall

# Upgrade / 升级
git pull
./install.sh --upgrade
```

## Upgrade Guide / 升级指南

```bash
cd nightmend
git pull
./install.sh --upgrade
```

The upgrade process:
1. Pulls latest code / 拉取最新代码
2. Rebuilds containers / 重建容器
3. Restarts services / 重启服务
4. Runs new migrations / 执行新迁移

**Data is preserved** — volumes are not removed during upgrades.

## Troubleshooting / 常见问题

### Docker not found / 未找到 Docker
```bash
curl -fsSL https://get.docker.com | sh
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in / 重新登录
```

### Port already in use / 端口被占用
```bash
# Check what's using the port / 检查端口占用
lsof -i :8001
# Re-run installer with different ports / 使用不同端口重装
./install.sh
```

### Database connection failed / 数据库连接失败
```bash
# Check postgres container / 检查数据库容器
docker compose logs postgres
docker compose exec postgres pg_isready -U nightmend
```

### Backend won't start / 后端无法启动
```bash
docker compose logs backend
# Common fix: rebuild / 常见修复：重建
docker compose build backend --no-cache
docker compose up -d backend
```

### Reset admin password / 重置管理员密码
```bash
docker compose exec postgres psql -U nightmend -d nightmend -c \
  "UPDATE users SET hashed_password='\$2b\$12\$LJ3m4ys3gz...' WHERE username='admin';"
```

### Firewall / 防火墙
```bash
# CentOS/RHEL
firewall-cmd --permanent --add-port=3001/tcp --add-port=8001/tcp
firewall-cmd --reload

# Ubuntu/Debian
ufw allow 3001/tcp
ufw allow 8001/tcp
```
