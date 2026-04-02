# NightMend 部署指南

## 系统要求

| 项目 | 最低要求 | 推荐 |
|------|---------|------|
| **操作系统** | Ubuntu 22.04 / Debian 12 / CentOS Stream 9 | Ubuntu 24.04 |
| **CPU** | 2 核 | 4 核 |
| **内存** | 2 GB | 4 GB |
| **磁盘** | 20 GB | 50 GB |
| **网络** | 可访问外网（拉取 Docker 镜像） | — |

需要开放的端口：
- **3001**（前端 Web，可自定义）
- **8001**（后端 API，可自定义）

---

## 快速安装（一行命令）

```bash
curl -fsSL https://raw.githubusercontent.com/LinChuang2008/nightmend/main/deploy/nightmend-deploy.sh | sudo bash
```

带 AI 功能：

```bash
curl -fsSL https://raw.githubusercontent.com/LinChuang2008/nightmend/main/deploy/nightmend-deploy.sh \
  | sudo bash -s -- --ai-key sk-your-key --domain your-domain.com
```

---

## 手动安装

### 1. 安装 Docker

```bash
# Ubuntu / Debian
curl -fsSL https://get.docker.com | sh
systemctl enable --now docker

# CentOS Stream 9
dnf install -y dnf-plugins-core
dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
dnf install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
systemctl enable --now docker
```

### 2. 获取代码

```bash
git clone https://github.com/LinChuang2008/nightmend.git /opt/nightmend
cd /opt/nightmend
```

### 3. 配置环境变量

```bash
cp deploy/.env.example .env
# 编辑 .env，至少修改以下项：
#   POSTGRES_PASSWORD=<随机强密码>
#   JWT_SECRET_KEY=<随机强密码>
#   AI_API_KEY=<你的 DeepSeek API Key>
```

或手动生成密码：

```bash
openssl rand -base64 32  # 数据库密码
openssl rand -base64 48  # JWT 密钥
```

### 4. 启动服务

```bash
cp deploy/docker-compose.prod.yml .
docker compose -f docker-compose.prod.yml up -d
```

### 5. 验证

```bash
# 检查容器状态
docker compose -f docker-compose.prod.yml ps

# 检查后端
curl http://localhost:8001/docs

# 浏览器访问前端
# http://your-ip:3001
```

### 6. 创建管理员

```bash
curl -X POST http://localhost:8001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password","email":"admin@example.com","role":"admin"}'
```

---

## 配置说明

### 环境变量一览

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POSTGRES_PASSWORD` | — | **必填** 数据库密码 |
| `JWT_SECRET_KEY` | — | **必填** JWT 签名密钥 |
| `FRONTEND_PORT` | 3001 | 前端访问端口 |
| `BACKEND_PORT` | 8001 | 后端 API 端口 |
| `AI_API_KEY` | — | AI 服务 API Key |
| `AI_MODEL` | deepseek-chat | AI 模型名称 |
| `AI_API_BASE` | https://api.deepseek.com/v1 | AI API 地址 |
| `MEMORY_ENABLED` | false | 是否启用运维记忆系统 |
| `AGENT_ENABLED` | false | 是否启用自动修复 |
| `AGENT_DRY_RUN` | true | 自动修复 dry-run 模式 |

### AI 功能配置

NightMend 支持所有 OpenAI 兼容的 API。推荐使用 [DeepSeek](https://platform.deepseek.com/)（成本低）。

```bash
# .env
AI_API_KEY=sk-your-key
AI_MODEL=deepseek-chat
AI_API_BASE=https://api.deepseek.com/v1
```

配置后可使用：
- AI 对话运维问答
- 告警根因分析
- 日志异常分析
- AI 拓扑建议

---

## Agent 安装

Agent 部署在被监控的目标主机上，负责采集指标、日志和服务状态。

### 安装

```bash
# 在目标主机上
pip3 install git+https://github.com/LinChuang2008/nightmend.git#subdirectory=agent
```

### 获取 Token

1. 登录 NightMend Web 界面
2. 进入 **系统设置** → **Agent Token**
3. 创建新 Token，复制备用

### 配置并运行

```bash
mkdir -p /etc/nightmend
cat > /etc/nightmend/agent.conf <<EOF
[server]
url = http://your-nightmend-server:8001
token = your-agent-token

[collector]
interval = 60

[log]
level = INFO
EOF

# 运行 Agent
nightmend-agent --config /etc/nightmend/agent.conf
```

### systemd 托管（推荐）

```bash
cat > /etc/systemd/system/nightmend-agent.service <<EOF
[Unit]
Description=NightMend Monitoring Agent
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/nightmend-agent --config /etc/nightmend/agent.conf
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now nightmend-agent
```

---

## 常用运维命令

```bash
cd /opt/nightmend

# 查看状态
docker compose -f docker-compose.prod.yml ps

# 查看日志
docker compose -f docker-compose.prod.yml logs -f
docker compose -f docker-compose.prod.yml logs backend  # 仅后端

# 重启
docker compose -f docker-compose.prod.yml restart

# 停止
docker compose -f docker-compose.prod.yml down

# 更新版本
git pull
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# 数据库备份
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U nightmend nightmend > backup_$(date +%Y%m%d).sql
```

---

## 常见问题

### Q: 容器启动失败，提示端口占用

```bash
# 查看端口占用
ss -tlnp | grep -E '3001|8001'
# 修改 .env 中的 FRONTEND_PORT 或 BACKEND_PORT
```

### Q: 后端启动超时

```bash
# 查看后端日志
docker compose -f docker-compose.prod.yml logs backend
# 常见原因：数据库未就绪，等待几秒后重启
docker compose -f docker-compose.prod.yml restart backend
```

### Q: AI 功能不可用

检查 `.env` 中 `AI_API_KEY` 是否正确配置，并确认 API 可访问：

```bash
curl https://api.deepseek.com/v1/models -H "Authorization: Bearer sk-your-key"
```

### Q: Agent 注册失败

1. 确认 Agent Token 已在 Web 界面创建
2. 确认目标主机能访问 NightMend 后端（`curl http://server:8001/docs`）
3. 检查 Agent 日志：`journalctl -u nightmend-agent -f`

### Q: 忘记管理员密码

```bash
# 进入后端容器重置
docker compose -f docker-compose.prod.yml exec backend python -c "
from app.database import SessionLocal
from app.models.user import User
from passlib.context import CryptContext
pwd = CryptContext(schemes=['bcrypt'])
db = SessionLocal()
user = db.query(User).filter(User.username=='admin').first()
user.hashed_password = pwd.hash('new-password')
db.commit()
print('密码已重置')
"
```

### Q: 如何配置 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name monitor.example.com;

    location / {
        proxy_pass http://127.0.0.1:3001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### Q: 如何迁移数据

```bash
# 导出
docker compose -f docker-compose.prod.yml exec postgres \
  pg_dump -U nightmend nightmend > nightmend_backup.sql

# 导入（在新服务器）
docker compose -f docker-compose.prod.yml exec -T postgres \
  psql -U nightmend nightmend < nightmend_backup.sql
```

---

## 技术支持

- GitHub Issues: https://github.com/LinChuang2008/nightmend/issues
- 文档: https://github.com/LinChuang2008/nightmend/wiki
