<div align="center">

# VigilOps

**Your team gets 200+ alerts daily. 80% are noise. AI fixes them while you sleep.**

[![Stars](https://img.shields.io/github/stars/LinChuang2008/vigilops?style=for-the-badge&logo=github&color=gold)](https://github.com/LinChuang2008/vigilops)
[![CI](https://img.shields.io/github/actions/workflow/status/LinChuang2008/vigilops/test.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/LinChuang2008/vigilops/actions/workflows/test.yml)
[![Docker](https://img.shields.io/github/actions/workflow/status/LinChuang2008/vigilops/docker-publish.yml?branch=main&style=for-the-badge&label=Docker&logo=docker)](https://github.com/LinChuang2008/vigilops/actions/workflows/docker-publish.yml)
[![Version](https://img.shields.io/badge/version-v2026.03.29-blue?style=for-the-badge)](https://github.com/LinChuang2008/vigilops/releases)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue?style=for-the-badge)](LICENSE)

[Live Demo](https://demo.lchuangnet.com/login) | [Install](#quickstart) | [Docs](#documentation) | [中文文档](README.zh-CN.md)

<br/>

![VigilOps Demo — Alert → AI Analysis → Auto-Fix in 47s](docs/screenshots/demo-animation.svg)

</div>

---

## What Makes VigilOps Different

You've tried **Grafana + Prometheus**. You know **Datadog**. They tell you *something broke*. None of them **fix it**.

VigilOps is the **first open-source AI platform** that doesn't just monitor — it **heals**:

1. **AI Analyzes** — DeepSeek reads logs, metrics, topology to find the real cause
2. **AI Decides** — Picks the right Runbook from 13 built-in auto-remediation scripts
3. **AI Fixes** — Executes the fix with safety checks and approval workflows
4. **AI Learns** — Same problems get resolved faster next time

**Global First**: World's first open-source monitoring platform with **MCP (Model Context Protocol)** integration — your AI coding assistant can query live production data directly.

---

## Quickstart

**Try Online** (no install): [demo.lchuangnet.com](https://demo.lchuangnet.com/login) — `demo@vigilops.io` / `demo123`

**Self-Host in 3 Steps:**

```bash
git clone https://github.com/LinChuang2008/vigilops.git && cd vigilops
cp .env.example .env                    # Optional: add DeepSeek API key for live AI
docker compose up -d                    # Open http://localhost:3001
```

> First registered account becomes admin. On first startup, the backend auto-creates tables, alert rules, and dashboard components.

---

## Feature Comparison

| Feature | VigilOps | Nightingale | Prom+Grafana | Datadog | Zabbix |
|---------|:--------:|:-----------:|:------------:|:-------:|:------:|
| AI Root Cause Analysis | Built-in | - | - | Enterprise | - |
| Auto-Remediation | 13 Runbooks | - | - | Enterprise | - |
| MCP Integration | **First** | - | - | Early | - |
| PromQL Queries | ✓ | - | Native | Enterprise | - |
| Self-Hosted | Docker | K8s/Docker | Complex | SaaS | Yes |
| Cost | **Free** | Free/Ent | Free | $$$ | Free/Ent |
| Setup Time | **5 min** | 30 min | 2+ hrs | 5 min | 1+ hr |

**Sweet Spot**: Small-to-medium teams who want AI-powered ops without enterprise licensing costs.

> **Honest disclaimer**: We're early stage. For mission-critical systems at scale, use proven solutions. For teams ready to experiment with AI ops, we're your best bet.

---

## How It Works

```
  Alert Fires        AI Diagnosis          Auto-Fix              Resolved
  ┌──────────┐     ┌──────────────┐     ┌────────────────┐    ┌────────────┐
  │ Disk 95% │────>│ "Log rotation│────>│ log_rotation   │───>│ Disk 60%   │
  │ on prod  │     │  needed on   │     │ runbook starts │    │ Fixed in   │
  │ server   │     │  /var/log"   │     │ safely         │    │ 2 minutes  │
  └──────────┘     └──────────────┘     └────────────────┘    └────────────┘
```

**13 Built-in Runbooks**: `disk_cleanup` | `service_restart` | `memory_pressure` | `log_rotation` | `zombie_killer` | `connection_reset` | `cpu_high` | `docker_cleanup` | `network_diag` | `mysql_health` | `redis_health` | `nginx_fix` | `swap_pressure`

**AI Runbook Generator**: Describe a scenario in natural language, and AI generates an executable Runbook with safety checks — via `/api/v1/ai/generate-runbook`.

---

## Prometheus AlertManager Bridge

Already running Prometheus? Add 3 lines to `alertmanager.yml` and get AI diagnosis on every alert:

```yaml
receivers:
  - name: 'vigilops'
    webhook_configs:
      - url: 'http://your-vigilops:8001/api/v1/webhooks/alertmanager'
        http_config:
          authorization:
            type: Bearer
            credentials: 'YOUR_TOKEN'
route:
  receiver: 'vigilops'
```

**What happens**: Prometheus fires alert → VigilOps receives it → AI analyzes root cause → diagnosis appears in real-time on the Demo page via SSE.

Two modes: **Diagnosis-only** (safe, read-only analysis) or **Auto-remediation** (AI picks and executes the right Runbook).

---

## Screenshots

<div align="center">

**Dashboard** — Real-time metrics across all hosts
![Dashboard](docs/screenshots/dashboard.jpg)

**AI Alert Analysis** — Root cause + recommended action
![AI Analysis](docs/screenshots/ai-analysis.jpg)

</div>

---

## MCP Integration — Global Open Source First

Your AI assistant (Claude Code, Cursor) queries live production data via MCP:

```bash
# Enable in backend/.env
VIGILOPS_MCP_ENABLED=true
VIGILOPS_MCP_PORT=8003
VIGILOPS_MCP_API_KEY=your-secret-token
```

> **Note**: Authentication via `VIGILOPS_MCP_API_KEY` is required in production.

**5 MCP Tools**: `get_servers_health` | `get_alerts` | `search_logs` | `analyze_incident` | `get_topology`

Ask your AI: *"Show all critical alerts on prod-server-01"* / *"Analyze last night's CPU spike"* / *"Search for OOM errors in the past 2 hours"*

---

## PromQL Query Support

Query metrics using familiar PromQL syntax via API:

```bash
# Instant query
GET /api/v1/promql/query?query=vigilops_host_cpu_percent

# Range query
GET /api/v1/promql/query_range?query=avg(vigilops_host_cpu_percent)&start=...&end=...&step=5m

# Supported: rate(), avg(), sum(), min(), max(), count(), avg_over_time(), label matchers
```

Compatible with Prometheus HTTP API format for Grafana integration.

---

## Agent — Cross-Platform Monitoring

The VigilOps Agent collects system metrics, discovers services, and monitors databases. It runs on **Linux**, **Windows/Windows Server**, and **macOS**.

**Linux:**
```bash
pip install vigilops-agent
vigilops-agent run -c /etc/vigilops/agent.yaml
```

**Windows (PowerShell):**
```powershell
.\scripts\install-windows-agent.ps1 -ServerUrl "http://your-server:8001" -Token "your-token"
.\scripts\install-windows-service.ps1   # Register as Windows Service
```

| Feature | Linux | Windows | macOS |
|---------|:-----:|:-------:|:-----:|
| CPU / Memory / Disk / Network | ✓ | ✓ | ✓ |
| Docker Service Discovery | ✓ | ✓ | ✓ |
| Host Service Discovery | ✓ (ss) | ✓ (netstat) | - |
| Database Monitoring | ✓ | ✓ | ✓ |
| Log Collection | ✓ | ✓ | ✓ |

---

## Installation

### Prerequisites
- Docker 20+ & Docker Compose v2+
- 4 CPU / 8 GB RAM (build) / 2 GB RAM (runtime)

### Environment Variables

| Variable | Required | Description |
|----------|:--------:|-------------|
| `POSTGRES_PASSWORD` | Yes | Database password |
| `JWT_SECRET_KEY` | Yes | `openssl rand -hex 32` |
| `AI_API_KEY` | Yes | DeepSeek API key |
| `AI_AUTO_SCAN` | Rec. | Auto-analyze alerts (`true`) |

See [docs/installation.md](docs/installation.md) for full guide.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, TypeScript, Vite, Ant Design 6, ECharts 6 |
| Backend | Python 3.9+, FastAPI, SQLAlchemy, AsyncIO |
| Database | PostgreSQL 15+, Redis 7+ |
| AI | DeepSeek API (configurable LLM) |
| Agent | Python 3.9+, psutil — Linux / Windows / macOS |
| Deploy | Docker Compose, Helm Chart (K8s) |

---

## Documentation

[Getting Started](docs/getting-started.md) | [Installation](docs/installation.md) | [User Guide](docs/user-guide.md) | [API Reference](docs/api-reference.md) | [Architecture](docs/architecture.md) | [Contributing](CONTRIBUTING.md) | [Changelog](CHANGELOG.md)

---

## Contributing

We need contributors who understand alert fatigue firsthand. See [CONTRIBUTING.md](CONTRIBUTING.md).

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d
pip install -r requirements-dev.txt
cd frontend && npm install
```

---

## Community

- [GitHub Discussions](https://github.com/LinChuang2008/vigilops/discussions)
- [Report a Bug](https://github.com/LinChuang2008/vigilops/issues/new)
- Email: [lchuangnet@lchuangnet.com](mailto:lchuangnet@lchuangnet.com)

---

<div align="center">

[Apache 2.0](LICENSE) — Use it, fork it, ship it commercially.

[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>
