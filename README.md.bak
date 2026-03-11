<div align="center">

# 🛡️ VigilOps

**Your team is drowning in alerts. Most of them don't matter. VigilOps fixes that.**

[![Stars](https://img.shields.io/github/stars/LinChuang2008/vigilops?style=social)](https://github.com/LinChuang2008/vigilops)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Version](https://img.shields.io/badge/version-v0.9.1-blue)](https://github.com/LinChuang2008/vigilops/releases)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://github.com/LinChuang2008/vigilops)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[🌐 Website](https://www.lchuangnet.com) · [🎯 Live Demo](https://demo.lchuangnet.com) · [Docs](#-documentation) · [中文](#-中文)

</div>

---

## The Problem

You set up Prometheus and Grafana. You configured alert rules. Now you get 200+ alerts per day, and 80% are noise. Your on-call engineer gets woken up at night for issues that either resolve themselves or could be fixed with a simple script.

**The monitoring industry has a dirty secret: most tools are great at telling you something is wrong, but terrible at doing anything about it.**

VigilOps takes a different approach. Instead of just sending you more alerts, it:

1. **Analyzes** each alert with AI (DeepSeek) to determine root cause
2. **Decides** if it can be auto-fixed using a built-in Runbook
3. **Fixes** the issue automatically (with safety checks and approval workflows)
4. **Learns** — so the same type of issue gets resolved faster next time

The result: fewer alerts that wake you up, faster resolution when something real happens.

> ⚠️ **Honest disclaimer**: VigilOps is an early-stage open source project. It works, it's deployed in real environments, but it's not battle-tested at scale yet. We're looking for early adopters who want to shape the product. If you need enterprise-grade reliability today, Datadog or PagerDuty are safer choices.

---

## See It In Action

```
  Alert Triggered        AI Diagnoses           Runbook Executes        Resolved
  ┌──────────┐        ┌───────────────┐        ┌────────────────┐     ┌──────────┐
  │ Disk 95% │───────▶│ Root Cause    │───────▶│ disk_cleanup   │────▶│ Disk 60% │
  │ Alert    │        │ Analysis      │        │ runbook runs   │     │ ✅ Fixed  │
  └──────────┘        └───────────────┘        └────────────────┘     └──────────┘
       │                      │                         │
   Monitors               DeepSeek AI             Safety checks +
   detect issue           correlates logs          approval before
                          & metrics                execution
```

**6 Built-in Runbooks** — ready out of the box:

| Runbook | What it does |
|---------|-------------|
| 🧹 `disk_cleanup` | Clears temp files, old logs, reclaims disk space |
| 🔄 `service_restart` | Gracefully restarts failed services |
| 💾 `memory_pressure` | Identifies and mitigates memory-hogging processes |
| 📝 `log_rotation` | Rotates and compresses oversized logs |
| 💀 `zombie_killer` | Detects and terminates zombie processes |
| 🔌 `connection_reset` | Resets stuck connections and connection pools |

---

## Screenshots

<div align="center">

**Dashboard — real-time metrics across all monitored hosts**
![Dashboard](docs/screenshots/dashboard.jpg)

**AI Alert Analysis — root cause, severity, and recommended action**
![AI Analysis](docs/screenshots/ai-analysis.jpg)

**Alert List — with AI-powered triage and auto-remediation status**
![Alerts](docs/screenshots/alerts.jpg)

**Auto-Remediation — automated runbook execution with audit trail**
![Auto-Remediation](docs/screenshots/topology.jpg)

</div>

---

## Quick Start

```bash
git clone https://github.com/LinChuang2008/vigilops.git
cd vigilops
cp .env.example .env   # Edit with your DeepSeek API key
docker compose up -d
```

Open `http://localhost:3001`. That's it.

**🎯 Don't want to install? Try the live demo:**

> 🌐 **Official Website**: [www.lchuangnet.com](https://www.lchuangnet.com)
> 🎯 **Live Demo**: [demo.lchuangnet.com](https://demo.lchuangnet.com) — Login: `demo@vigilops.io` / `demo123` (read-only)
>
> ⚠️ This is a single demo server — it may be slow or temporarily down. For real evaluation, self-host it.

---

## 🚀 Deployment Guide

### Prerequisites

- Docker 20+ and Docker Compose v2+
- 4 CPU cores / 8 GB RAM (for first-time build with image compilation; runtime requires ~2 GB)
- Ports 3001 (frontend) and 8001 (backend) available

---

### 1. Local Development (Quick Start)

```bash
# 1. Clone the repository
git clone https://github.com/LinChuang2008/vigilops.git
cd vigilops

# 2. Configure environment variables
cp backend/.env.example backend/.env
# Edit backend/.env — set at minimum:
#   AI_API_KEY=<your DeepSeek API key>

# 3. Start all services
docker compose up -d

# 4. Wait for services to be ready
# First run takes 15–30 min (image pull + build). Subsequent restarts: <60s.
until curl -s http://localhost:8001/health > /dev/null; do echo "Waiting..."; sleep 10; done && echo "Ready!"

# 5. Open the frontend
# http://localhost:3001
# Register the first account — it is automatically granted admin rights.
```

> 💡 For the development environment you can also use the built-in test account: `admin` / `vigilops` (dev only, not available in production).

---

### 2. Production Deployment (Linux / VPS / Cloud)

```bash
# Requirements: Docker 20+ / Docker Compose v2+

# 1. Clone to the server
git clone https://github.com/LinChuang2008/vigilops.git /opt/vigilops
cd /opt/vigilops

# 2. Configure production environment variables
cp .env.example .env
# You MUST change the following values:
#   POSTGRES_PASSWORD  — use a strong password
#   JWT_SECRET_KEY     — random string, generate with: openssl rand -hex 32
#   AI_API_KEY         — your DeepSeek API key
#   AI_AUTO_SCAN       — set to true to enable automatic alert scanning

# 3. Start services
docker compose up -d

# 4. Check status
docker compose ps
docker compose logs backend --tail=50

# 5. Open the frontend
# http://<your-server-ip>:3001
# Register the first account — it is automatically granted admin rights.
```

> ⚠️ **Security reminder**: Never commit `.env` to version control. All default passwords in `.env.example` must be changed before going to production.

---

### 3. Environment Variables Reference

| Variable | Description | Example / Default |
|---|---|---|
| `POSTGRES_PASSWORD` | PostgreSQL password | `change-me` (**required**) |
| `POSTGRES_DB` | Database name | `vigilops` |
| `POSTGRES_USER` | Database user | `vigilops` |
| `JWT_SECRET_KEY` | JWT signing secret | `change-me-in-production` (**required**) |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Access token TTL (minutes) | `120` |
| `AI_PROVIDER` | AI backend | `deepseek` |
| `AI_API_KEY` | DeepSeek (or compatible) API key | _(empty, **required**)_ |
| `AI_API_BASE` | AI API endpoint | `https://api.deepseek.com/v1` |
| `AI_MODEL` | Model name | `deepseek-chat` |
| `AI_AUTO_SCAN` | Auto-scan new alerts with AI | `false` |
| `AGENT_ENABLED` | Enable auto-remediation | `false` |
| `AGENT_DRY_RUN` | Dry-run mode (log only, no execution) | `true` |
| `AGENT_MAX_AUTO_PER_HOUR` | Max auto-remediations per hour | `10` |
| `BACKEND_PORT` | Host port for backend | `8001` |
| `FRONTEND_PORT` | Host port for frontend | `3001` |

> 💡 Run `openssl rand -hex 32` to generate a secure random value for `JWT_SECRET_KEY` and `POSTGRES_PASSWORD`.

---

### 4. Installing the VigilOps Agent (Monitored Servers)

The VigilOps Agent is a lightweight Python process that collects metrics, checks service health, and tails logs on each monitored host, then reports data to the VigilOps backend.

**Requirements**: Linux (Ubuntu / Debian / CentOS / RHEL / Rocky / Alma), Python ≥ 3.9, root access.

#### Getting an Agent Token

1. Log in to VigilOps → **Server Management** → **Add Server**
2. Copy the generated Agent Token from the dialog

#### Quick install (one-liner)

```bash
# Run on the server you want to monitor
curl -fsSL http://<your-vigilops-server>:8001/agent/install.sh | \
  VIGILOPS_SERVER=http://<your-vigilops-server>:8001 \
  AGENT_TOKEN=<token-from-ui> \
  bash
```

#### Manual installation

```bash
# 1. Copy the agent directory to the monitored server
scp -r vigilops/agent user@monitored-host:/opt/vigilops-agent

# 2. Install dependencies
cd /opt/vigilops-agent
pip3 install -r requirements.txt

# 3. Create config file
cp config.example.yml config.yml
# Edit config.yml — set server.url and server.token

# 4. Start with systemd
cp vigilops-agent.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now vigilops-agent
```

> See [docs/agent-guide.md](docs/agent-guide.md) for full configuration options, multi-host batch deployment, and troubleshooting.

---

### 5. Upgrading

```bash
cd /opt/vigilops
git pull origin main
docker compose down
docker compose up -d --build --no-cache
```

---

### 6. FAQ

**Q: Port 3001 or 8001 is already in use — what do I do?**

Set `FRONTEND_PORT` and/or `BACKEND_PORT` in `backend/.env` before starting:
```bash
FRONTEND_PORT=3002 BACKEND_PORT=8002 docker compose up -d
```

**Q: I forgot the admin password. How do I reset it?**

```bash
docker compose exec backend python3 -c "
import asyncio
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import update

async def reset():
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(User).where(User.email == 'your@email.com')
            .values(hashed_password=get_password_hash('NewPassword123!'))
        )
        await db.commit()
        print('Password reset OK')

asyncio.run(reset())
"
```

**Q: How do I back up data?**

```bash
bash scripts/backup.sh
# Scheduled backup (add to cron):
# 0 2 * * * cd /opt/vigilops && bash scripts/backup.sh >> logs/backup.log 2>&1
```

**Q: How do I view backend logs?**

```bash
docker compose logs backend -f --tail=100
```

**Q: Are ClickHouse and Loki required?**

No. Both are optional log backends. The default is PostgreSQL, which works out of the box.  
- ClickHouse: set `LOG_BACKEND=clickhouse` in `.env`  
- Loki: start with `docker compose --profile loki up -d`

---

## MCP Integration (AI Agent Access)

VigilOps ships a built-in **MCP Server** so AI coding assistants like Claude Code and Cursor can query live production data — alerts, logs, server health, topology — directly from the chat interface.

### Enabling the MCP Server

The MCP Server runs inside the backend container. It is **disabled by default**. To enable it, add the following to `backend/.env`:

```env
VIGILOPS_MCP_ENABLED=true
VIGILOPS_MCP_HOST=0.0.0.0   # bind to all interfaces (required for remote access)
VIGILOPS_MCP_PORT=8003       # default port
```

Then restart the backend:

```bash
docker compose restart backend
# Verify it is listening:
curl http://localhost:8003/
```

### Connecting Claude Desktop / Claude Code

The MCP Server speaks HTTP (FastMCP + uvicorn). Add it to your Claude Desktop config (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "vigilops": {
      "type": "http",
      "url": "http://localhost:8003/mcp"
    }
  }
}
```

For a **remote server**, replace `localhost:8003` with your server's IP or domain:

```json
{
  "mcpServers": {
    "vigilops": {
      "type": "http",
      "url": "http://139.196.210.68:8003/mcp"
    }
  }
}
```

> 🔐 The MCP Server requires Bearer Token authentication. Add the following to your `backend/.env` to set the token:
> ```env
> VIGILOPS_MCP_TOKEN=your-secret-token-here
> ```
> Then include the token in your MCP client config. Always restrict port 8003 via firewall in production.

### Available Tools (5 total)

| Tool | Description |
|------|-------------|
| `get_servers_health` | Get health status and metrics for all monitored servers |
| `get_alerts` | Query alert list — filter by status, severity, or host |
| `search_logs` | Search logs by keyword and time range |
| `analyze_incident` | AI-powered root cause analysis with fix recommendations |
| `get_topology` | Retrieve service dependency topology data |

### Usage Examples

Once connected, you can ask your AI assistant:

```
"Check the current alerts on prod-server-01"
"Analyze the root cause of last night's CPU spike"
"Search for OOM errors in the last 2 hours"
"What is the health status of all servers right now?"
```

---

## What's Inside

- **AI Root Cause Analysis** — DeepSeek analyzes logs, metrics, and topology to explain *why* something broke
- **Auto-Remediation** — 6 built-in Runbooks with safety checks; AI picks the right one and runs it
- **MCP Server** — 5 MCP tools for AI Agent integration (query alerts, run diagnostics, execute runbooks)
- **Full-Stack Monitoring** — Servers (CPU/mem/disk/net), services (HTTP/TCP/gRPC), databases (PostgreSQL/MySQL)
- **Smart Alerting** — Metric, log keyword, and DB threshold rules with noise reduction and cooldown
- **Alert Escalation** — Auto-escalation policies with on-call calendar and coverage analysis
- **Log Management** — Multi-backend support: PostgreSQL, ClickHouse, or Loki
- **Service Topology** — Interactive dependency maps with health overlay
- **5 Notification Channels** — DingTalk, Feishu (Lark), WeCom, Email, Webhook
- **SLA Tracking** — Uptime SLOs, error budgets, violation alerts
- **i18n** — Chinese and English UI with ~300 translation keys
- **24 Dashboard Pages** — Built with React 19 + TypeScript + Ant Design 6

---

## Honest Comparison

We believe in transparent positioning. Here's how VigilOps compares — including where we fall short:

| | VigilOps | Nightingale (夜莺) | Prometheus+Grafana | Datadog | Zabbix |
|---|---|---|---|---|---|
| **AI Root Cause Analysis** | ✅ Built-in | ❌ | ❌ | 💰 Add-on | ❌ |
| **Auto-Remediation** | ✅ 6 Runbooks | ❌ | ❌ | 💰 Enterprise | ❌ |
| **MCP Integration** | ✅ 5 tools | ❌ | ❌ | 🟡 Early | ❌ |
| **Self-Hosted** | ✅ | ✅ | ✅ | ❌ | ✅ |
| **Open Source** | ✅ Apache 2.0 | ✅ Apache 2.0 | ✅ | ❌ | ✅ GPL |
| **Setup Complexity** | Low (Docker) | Low | High (multi-component) | Low (SaaS) | Medium |
| **Community Size** | 🔴 Small (new project) | ⭐ 8k+ stars | ⭐⭐⭐ Massive | N/A | ⭐⭐ Large |
| **Production Maturity** | 🔴 Early stage | ✅ 1000+ enterprises | ✅ Industry standard | ✅ Industry leader | ✅ Decades |
| **High Availability** | 🔴 Single-node only | ✅ | ✅ | ✅ | ✅ |
| **Scale (hosts)** | 🟡 Tested <50 | ✅ 1000+ | ✅ 10000+ | ✅ Unlimited | ✅ 10000+ |
| **Ecosystem / Plugins** | 🔴 Limited | 🟡 Growing | ✅ Huge | ✅ 700+ | ✅ Large |
| **Cost** | Free | Free / Enterprise paid | Free | $$$$ | Free / Enterprise paid |

**Where we're strong**: AI-driven alert analysis and auto-remediation in a single open-source package. No other open-source tool does this today.

**Where we're weak**: Community size, production maturity, and scale. We're honest about this — VigilOps is best suited for small-to-medium teams (< 50 hosts) who want to experiment with AI-powered operations.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19, TypeScript, Vite, Ant Design 6, ECharts 6 |
| **Backend** | Python 3.9+, FastAPI, SQLAlchemy |
| **Database** | PostgreSQL 15+, Redis 7+ |
| **Log Storage** | PostgreSQL / ClickHouse / Loki (configurable) |
| **AI** | DeepSeek API (configurable LLM endpoint) |
| **Deployment** | Docker Compose |

## Architecture

```
┌──────────────────────────────────────────────────┐
│              React 19 Frontend                    │
│          (TypeScript + Vite + Ant Design 6)       │
└───────────────────┬──────────────────────────────┘
                    │ REST / WebSocket
┌───────────────────▼──────────────────────────────┐
│              FastAPI Backend                       │
│  ┌──────────┐ ┌───────────┐ ┌──────────────────┐ │
│  │ 29       │ │ Alerting  │ │ AI Agent         │ │
│  │ Routers  │ │ + Escala- │ │ + Runbook Engine │ │
│  │          │ │ tion      │ │ + MCP Server     │ │
│  └────┬─────┘ └────┬──────┘ └────────┬─────────┘ │
│       └─────────────┼────────────────┘            │
│              Core Services (13)                    │
└──────┬──────────────┼────────────────────────────┘
       │              │
┌──────▼──────┐ ┌─────▼──────┐
│ PostgreSQL  │ │   Redis    │
│ (data +     │ │ (cache +   │
│  logs)      │ │  pub/sub)  │
└─────────────┘ └────────────┘
```

---

## Documentation

| Doc | Description |
|-----|-------------|
| [Getting Started](docs/getting-started.md) | First-time setup guide |
| [Installation](docs/installation.md) | Docker / manual deploy + env vars |
| [User Guide](docs/user-guide.md) | Full feature walkthrough |
| [API Reference](docs/api-reference.md) | REST API docs |
| [Architecture](docs/architecture.md) | System design + data flow |
| [Contributing](docs/contributing.md) | Dev environment + code standards |
| [Changelog](docs/changelog.md) | Version history |

## Developer Workflow

For contributors and internal developers, use the following scripts to validate changes before pushing:

```bash
# 1. Start local environment
docker compose up -d

# 2. Verify all core APIs pass smoke tests
bash scripts/test-local.sh

# 3. If tests pass, push and deploy to ECS
git push origin main
bash scripts/deploy-ecs.sh
```

| Script | Purpose |
|--------|---------|
| `scripts/test-local.sh` | Smoke-tests health, auth, hosts, alerts, dashboard, topology against local Docker |
| `scripts/deploy-ecs.sh` | SSH to ECS, `git pull`, `docker compose build/up`, then verifies the remote health endpoint |

> **Options**: Override defaults with env vars — e.g. `BASE_URL=http://localhost:8001 bash scripts/test-local.sh`

---

## Contributing

We welcome contributions — especially from people who experience alert fatigue firsthand.

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d
pip install -r requirements-dev.txt
cd frontend && npm install
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

[Apache 2.0](LICENSE) — use it, fork it, ship it.

---

## 🇨🇳 中文

### 你的团队每天被几百条告警淹没？

大多数运维工程师都经历过这样的场景：Prometheus 告警规则配好了，钉钉群每天弹出 200+ 条告警，其中 80% 是噪音。真正需要处理的问题被淹没在告警洪流中，值班工程师被反复叫醒处理那些本可以用一个脚本解决的问题。

**监控行业有个公开的秘密：大多数工具擅长告诉你出了问题，但不擅长解决问题。**

VigilOps 走了一条不同的路。它不只是发送更多告警，而是：

1. **用 AI 分析**每条告警的根因（基于 DeepSeek）
2. **判断**是否可以通过内置 Runbook 自动修复
3. **自动修复**问题（带安全检查和审批流程）
4. **持续学习**，同类问题下次更快解决

结果：更少的无效告警打扰你，真正的问题更快被解决。

> ⚠️ **诚实声明**：VigilOps 是一个早期开源项目。它能工作，已在真实环境部署，但还未经过大规模生产验证。我们正在寻找愿意一起打磨产品的早期用户。如果你现在就需要企业级可靠性，Datadog 或夜莺是更成熟的选择。

### 快速开始

```bash
git clone https://github.com/LinChuang2008/vigilops.git
cd vigilops
cp .env.example .env   # 填入你的 DeepSeek API Key
docker compose up -d
```
> ⚠️ **安全提示**：生产部署前请务必修改 `.env` 中的所有默认密码（`JWT_SECRET_KEY`、`POSTGRES_PASSWORD` 等）。


打开 `http://localhost:3001` 即可使用。

**🎯 在线体验：** [https://demo.lchuangnet.com](https://demo.lchuangnet.com) — 账号 `demo@vigilops.io` / `demo123`（只读）

---

### 🚀 部署教程

#### 前置要求

- Docker 20+ 及 Docker Compose v2+
- 4核 CPU / 8 GB 内存（首次构建含镜像编译；运行期约需 2 GB）
- 端口 3001（前端）和 8001（后端）未被占用

---

#### 1. 本地开发部署

```bash
# 1. 克隆项目
git clone https://github.com/LinChuang2008/vigilops.git
cd vigilops

# 2. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，至少填入：
#   AI_API_KEY=<你的 DeepSeek API Key>

# 3. 启动所有服务
docker compose up -d

# 4. 等待服务就绪
# 首次启动约 15–30 分钟（含镜像拉取+构建），后续重启 <60 秒
until curl -s http://localhost:8001/health > /dev/null; do echo "等待中..."; sleep 10; done && echo "就绪！"

# 5. 访问前端
# http://localhost:3001
# 注册第一个账号，系统自动设为管理员。
```

> 💡 开发环境可使用内置测试账号：`admin` / `vigilops`（仅开发环境有效）

---

#### 2. 生产环境部署（Linux / VPS / 云服务器）

```bash
# 1. 克隆到服务器
git clone https://github.com/LinChuang2008/vigilops.git /opt/vigilops
cd /opt/vigilops

# 2. 配置生产环境变量
cp .env.example .env
# 必须修改以下值：
#   POSTGRES_PASSWORD  — 改为强密码
#   JWT_SECRET_KEY     — 随机字符串，可用 openssl rand -hex 32 生成
#   AI_API_KEY         — 填入你的 DeepSeek API Key
#   AI_AUTO_SCAN       — 改为 true 以启用告警自动分析

# 3. 启动服务
docker compose up -d

# 4. 查看状态
docker compose ps
docker compose logs backend --tail=50

# 5. 访问前端
# http://<你的服务器IP>:3001
# 注册第一个账号，系统自动设为管理员。
```

> ⚠️ 生产部署必须修改所有默认密码，`.env` 文件不要提交到 Git 仓库。

---

#### 3. 环境变量说明

| 变量 | 说明 | 默认值 |
|---|---|---|
| `POSTGRES_PASSWORD` | 数据库密码 | `change-me`（**必须修改**）|
| `JWT_SECRET_KEY` | JWT 签名密钥 | `change-me-in-production`（**必须修改**）|
| `AI_API_KEY` | DeepSeek API Key | _空_（**必填**）|
| `AI_AUTO_SCAN` | 是否自动用 AI 分析告警 | `false` |
| `AGENT_ENABLED` | 是否启用自动修复 | `false` |
| `AGENT_DRY_RUN` | Dry-run 模式（只记录不执行） | `true` |
| `BACKEND_PORT` | 后端宿主机端口 | `8001` |
| `FRONTEND_PORT` | 前端宿主机端口 | `3001` |

---

#### 4. 安装 VigilOps Agent（被监控服务器）

VigilOps Agent 是部署在被监控主机上的轻量级 Python 进程，负责采集指标、检查服务健康状态、采集日志，并上报到 VigilOps 后端。

**系统要求**：Linux（Ubuntu/Debian/CentOS/RHEL/Rocky/Alma），Python ≥ 3.9，root 权限。

**获取 Agent Token**：登录 VigilOps → **服务器管理** → **添加服务器** → 复制 Token

```bash
# 一键安装（在被监控服务器上执行）
curl -fsSL http://<VigilOps服务器>:8001/agent/install.sh | \
  VIGILOPS_SERVER=http://<VigilOps服务器>:8001 \
  AGENT_TOKEN=<从管理界面获取的Token> \
  bash
```

详细配置参见 [docs/agent-guide.md](docs/agent-guide.md)。

---

#### 5. 升级

```bash
cd /opt/vigilops
git pull origin main
docker compose down
docker compose up -d --build --no-cache
```

---

#### 6. 常见问题

**Q: 端口被占用怎么办？**

在 `backend/.env` 中修改端口：
```bash
FRONTEND_PORT=3002 BACKEND_PORT=8002 docker compose up -d
```

**Q: 忘记管理员密码怎么重置？**

```bash
docker compose exec backend python3 -c "
import asyncio
from app.core.security import get_password_hash
from app.db.session import AsyncSessionLocal
from app.models.user import User
from sqlalchemy import update

async def reset():
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(User).where(User.email == 'your@email.com')
            .values(hashed_password=get_password_hash('NewPassword123!'))
        )
        await db.commit()
        print('密码重置成功')

asyncio.run(reset())
"
```

**Q: 如何备份数据？**

```bash
bash scripts/backup.sh
# 定时备份（加入 cron）：
# 0 2 * * * cd /opt/vigilops && bash scripts/backup.sh >> logs/backup.log 2>&1
```

**Q: ClickHouse / Loki 是必须的吗？**

不是。默认使用 PostgreSQL 存储日志，开箱即用。  
- 使用 ClickHouse：在 `.env` 中设置 `LOG_BACKEND=clickhouse`  
- 使用 Loki：`docker compose --profile loki up -d`

---

### MCP 集成（AI Agent 接入）

VigilOps 内置 **MCP Server**，让 Claude Code、Cursor 等 AI 编程助手可以直接查询生产环境数据——告警、日志、服务器健康状态、拓扑结构——无需离开对话界面。

#### 启用 MCP Server

MCP Server 运行在 backend 容器内，**默认关闭**。在 `backend/.env` 中添加：

```env
VIGILOPS_MCP_ENABLED=true
VIGILOPS_MCP_HOST=0.0.0.0   # 允许外部访问（远程服务器必须设置）
VIGILOPS_MCP_PORT=8003       # 默认端口
```

重启 backend 生效：

```bash
docker compose restart backend
# 验证是否已启动：
curl http://localhost:8003/
```

#### 在 Claude Desktop / Claude Code 中接入

MCP Server 使用 HTTP 模式（FastMCP + uvicorn）。在 Claude Desktop 配置文件（`~/.claude/claude_desktop_config.json`）中添加：

```json
{
  "mcpServers": {
    "vigilops": {
      "type": "http",
      "url": "http://localhost:8003/mcp"
    }
  }
}
```

远程服务器将 `localhost:8003` 替换为服务器 IP：

```json
{
  "mcpServers": {
    "vigilops": {
      "type": "http",
      "url": "http://139.196.210.68:8003/mcp"
    }
  }
}
```

> 🔐 MCP Server 已内置 Bearer Token 认证。在 `backend/.env` 中添加：
> ```env
> VIGILOPS_MCP_TOKEN=your-secret-token-here
> ```
> 配置 MCP 客户端时需携带该 token。生产环境同时建议通过防火墙限制 8003 端口访问来源。

#### 可用工具（共 5 个）

| 工具名 | 功能 |
|--------|------|
| `get_servers_health` | 获取所有服务器健康状态和指标 |
| `get_alerts` | 查询告警列表，支持状态/严重性/主机过滤 |
| `search_logs` | 搜索日志，支持关键词和时间范围 |
| `analyze_incident` | AI 根因分析，生成修复建议 |
| `get_topology` | 获取服务拓扑图数据 |

#### 使用示例

接入后，可以这样使用 AI 助手：

```
"查一下 prod-server-01 最近的告警"
"分析一下今天凌晨的 CPU 告警根因"
"搜索最近 2 小时的 OOM 错误"
"所有服务器现在的健康状态怎么样？"
```

---

### 核心差异化

**夜莺让你看到问题，VigilOps 帮你修好问题。**

- ✅ AI 根因分析 + 自动修复 — 开源方案中唯一提供此能力
- ✅ 6 个内置 Runbook — 磁盘清理、服务重启、内存释放、日志轮转、僵尸进程、连接重置
- ✅ MCP Server — 5 个工具，支持 AI Agent 集成
- ✅ 全栈监控 — 服务器 / 服务 / 数据库 / 日志 / 拓扑
- ✅ 中英双语 — 完整的国际化支持
- ✅ Docker 一键部署 — 无复杂依赖

### 我们的不足（诚实说）

- 🔴 社区很小 — 这是一个新项目，还没有大规模用户验证
- 🔴 仅支持单节点 — 没有高可用方案
- 🔴 测试规模有限 — 建议 50 台主机以内
- 🔴 生态有限 — 插件和集成还很少

如果这些对你来说可以接受，欢迎试用并告诉我们你的反馈。每一位早期用户的声音都非常重要。

### 开发者工作流

贡献者和内部开发者请使用以下脚本，在推送前本地验证变更：

```bash
# 1. 启动本地环境
docker compose up -d

# 2. 跑核心接口冒烟测试
bash scripts/test-local.sh

# 3. 测试通过后推送并部署到 ECS
git push origin main
bash scripts/deploy-ecs.sh
```

| 脚本 | 作用 |
|------|------|
| `scripts/test-local.sh` | 对本地 Docker 环境跑健康/登录/hosts/alerts/dashboard/topology 冒烟测试 |
| `scripts/deploy-ecs.sh` | SSH 到 ECS，执行 `git pull` + `docker compose build/up`，并验证远端健康接口 |

> **自定义参数**：可通过环境变量覆盖默认值，例如：`BASE_URL=http://localhost:8001 bash scripts/test-local.sh`

---

### 联系我们

- [GitHub Discussions](https://github.com/LinChuang2008/vigilops/discussions) — 提问、建议、交流
- [报告 Bug](https://github.com/LinChuang2008/vigilops/issues/new)
- 📧 [lchuangnet@lchuangnet.com](mailto:lchuangnet@lchuangnet.com)

---

<div align="center">

<sub>Built with ❤️ by LinChuang · Apache 2.0</sub>

</div>
