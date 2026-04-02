# NightMend 快速入门

> 5 分钟内启动 NightMend，开始监控你的第一台服务器。

## 目录

- [系统要求](#系统要求)
- [一键安装](#一键安装)
- [首次登录](#首次登录)
- [添加第一台监控主机](#添加第一台监控主机)
- [下一步](#下一步)

---

## 系统要求

| 项目 | 最低要求 |
|------|---------|
| Docker | 20.0+ |
| Docker Compose | v2.0+（`docker compose` 命令） |
| CPU | 2 核 |
| 内存 | 4 GB |
| 磁盘 | 10 GB 可用空间 |
| 操作系统 | Linux / macOS / Windows (WSL2) |

检查版本：

```bash
docker --version
docker compose version
```

## 一键安装

```bash
# 克隆项目
git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend

# 复制环境配置
cp .env.example .env

# 启动所有服务
docker compose up -d
```

首次启动会拉取镜像并构建，约需 3-5 分钟。查看启动状态：

```bash
docker compose ps
```

所有服务状态显示 `running` 即为启动成功。

### 端口说明

| 服务 | 端口 | 说明 |
|------|------|------|
| 前端 | 3001 | Web 管理界面 |
| 后端 | 8001 | API 服务 |
| PostgreSQL | 5433 | 数据库（映射到宿主机 5433，容器内 5432） |
| Redis | 6380 | 缓存（映射到宿主机 6380，容器内 6379） |

## 首次登录

1. 浏览器打开 [http://localhost:3001](http://localhost:3001)
2. 点击 **注册**，创建第一个账号
3. **第一个注册的用户自动成为管理员**，拥有全部权限

> 💡 如需快速体验，也可使用默认演示账号：`admin` / `nightmend`（仅开发环境）

## 添加第一台监控主机

### 第一步：创建 Agent Token

1. 登录后进入 **系统设置** → **Agent Token**
2. 点击 **创建 Token**，填写名称（如 `prod-server-01`）
3. 复制生成的 Token，后续安装 Agent 时需要

### 第二步：安装 Agent

在目标服务器上执行：

```bash
# 下载 Agent
git clone https://github.com/LinChuang2008/nightmend.git /opt/nightmend
cd /opt/nightmend/agent

# 安装依赖
pip install -r requirements.txt

# 配置 Agent
cat > /opt/nightmend/agent/.env << 'EOF'
NIGHTMEND_SERVER=http://<你的NightMend服务器IP>:8001
AGENT_TOKEN=<上一步复制的Token>
EOF

# 启动 Agent
python agent.py
```

使用 systemd 管理（推荐）：

```bash
cat > /etc/systemd/system/nightmend-agent.service << 'EOF'
[Unit]
Description=NightMend Agent
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/nightmend/agent
ExecStart=/usr/bin/python3 agent.py
Restart=always
RestartSec=10
EnvironmentFile=/opt/nightmend/agent/.env

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now nightmend-agent
```

### 第三步：验证数据

1. 回到 NightMend 前端，进入 **服务器列表**
2. 新添加的主机应在 1-2 分钟内出现
3. 点击主机名查看 CPU、内存、磁盘等监控数据

如果主机未出现，检查：

```bash
# 查看 Agent 日志
journalctl -u nightmend-agent -f

# 测试连通性
curl -s http://<NightMend服务器IP>:8001/api/health
```

## 下一步

- 📖 [详细安装指南](./installation.md) — 环境变量配置、手动部署、HTTPS、升级
- 📖 [API 文档](./api-reference.md) — 完整 REST API 参考
- 🤖 启用 AI 分析：在 `.env` 中配置 `AI_API_KEY`，获得智能告警分析和根因诊断
- 📊 配置告警规则：进入 **告警管理** → **告警规则**，创建指标/日志/数据库告警
- 🔔 配置通知渠道：支持钉钉、飞书、企业微信、邮件、Webhook
