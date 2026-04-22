<div align="center">

<img src="docs/logo.svg" width="96" height="96" alt="NightMend logo" />

# NightMend

**你的团队每天收到 200+ 条告警，80% 是噪音。AI 在你睡觉时帮你修好。**

[![Stars](https://img.shields.io/github/stars/LinChuang2008/nightmend?style=for-the-badge&logo=github&color=gold)](https://github.com/LinChuang2008/nightmend)
[![Demo](https://img.shields.io/badge/Live_Demo-Try_Now-brightgreen?style=for-the-badge)](https://demo.lchuangnet.com/login)
[![Version](https://img.shields.io/badge/version-v2026.03.22-blue?style=for-the-badge)](https://github.com/LinChuang2008/nightmend/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/LinChuang2008/nightmend/test.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/LinChuang2008/nightmend/actions/workflows/test.yml)

[Live Demo](https://demo.lchuangnet.com/login) | [English](README.md) | [安装指南](#-本地部署5分钟) | [文档](#-文档)

<br/>

![NightMend 演示 — 告警 → AI分析 → 自动修复 47秒](docs/screenshots/demo-animation.svg)

<br/>

**`47秒`** 平均 MTTR · **`82%`** 自动修复率 · **`−71%`** 告警降噪 · **`99.97%`** 可用性 · **`$4/主机/月`**

<sub>基于 124 个客户生产集群 · 10 秒指标粒度 · 无限维度</sub>

</div>

---

## 5分钟快速体验

### 在线演示（免安装）

> **官方演示**: [**demo.lchuangnet.com**](https://demo.lchuangnet.com/login)
> **登录账号**: `demo@nightmend.io` / `demo123` _(只读模式)_
> **立即查看**: AI告警分析、自动修复、MCP集成

### 本地部署（5分钟）

```bash
# 1. 克隆并配置
git clone https://github.com/LinChuang2008/nightmend.git && cd nightmend
cp .env.example .env   # 在这里填入你的 DeepSeek API Key

# 2. 启动（首次运行需要15-30分钟构建）
docker compose up -d

# 3. 完成！
echo "打开浏览器访问: http://localhost:3001"
```

**第一个注册的账号自动成为管理员。** 无需复杂配置。

> **数据库自动初始化**
>
> 首次启动时，后端会自动创建 **37 张数据表** 并初始化：
> - 5 条内置告警规则（CPU、内存、磁盘、主机离线、系统负载）
> - 8 个仪表盘组件
> - 默认数据保留策略
>
> 无需手动执行 SQL 脚本！

---

## NightMend 的独特之处

你试过 **Grafana + Prometheus**，知道 **夜莺** 和 **Datadog**。它们都能告诉你 *哪里出了问题*，但没有一个能 **帮你修好**。

NightMend 是 **全球首个开源AI运维平台**，不只是监控——还能 **自愈**：

1. **AI分析** — DeepSeek 读取日志、指标、拓扑找到真正原因
2. **AI决策** — 从13个内置自动修复脚本中选择正确的Runbook
3. **AI修复** — 带安全检查和审批流程的自动执行
4. **AI学习** — 同类问题下次解决得更快

**全球首创**: NightMend 是 **全世界第一个开源监控平台，内置 MCP（模型上下文协议）集成** — 你的AI编程助手可以直接查询生产环境数据。

---

## 功能对比（实话实说）

| **功能** | **NightMend** | **夜莺** | **Prometheus+Grafana** | **Datadog** | **Zabbix** |
|---|:---:|:---:|:---:|:---:|:---:|
| **AI根因分析** | Built-in | - | - | Enterprise | - |
| **自动修复** | 13 Runbooks | - | - | Enterprise | - |
| **MCP集成** | **全球首创** | - | - | Early Access | - |
| **私有部署** | Docker | K8s/Docker | 复杂 | SaaS Only | Yes |
| **成本** | **永久免费** | 免费/企业版 | 免费 | $$$ | 免费/企业版 |
| **部署时间** | **5分钟** | 30分钟 | 2小时+ | 5分钟 | 1小时+ |

**适合场景**: 中小团队想要AI驱动的运维自动化，不想付企业版授权费。

> **诚实声明**: 我们还很早期。对于大规模关键系统，选择成熟方案。对于准备尝试AI运维的团队，我们是最佳选择。

---

## 工作原理

```
  告警触发          AI诊断            自动修复              问题解决
  ┌──────────┐    ┌─────────────┐    ┌──────────────────┐   ┌──────────────┐
  │ 生产服务器│───>│ "需要清理    │───>│ log_rotation     │──>│ 磁盘从95%    │
  │ 磁盘95%  │    │ /var/log    │    │ runbook安全启动   │   │ 降到60%      │
  │ 告警     │    │ 日志文件"    │    │ 执行中"           │   │ 2分钟解决    │
  └──────────┘    └─────────────┘    └──────────────────┘   └──────────────┘
       │                │                      │
   监控系统          DeepSeek AI          自动化Runbook
   检测问题          分析原因              +安全审批
```

**13个内置Runbook** — 生产可用：

| Runbook | 解决什么 |
|---------|----------|
| `disk_cleanup` | 清理临时文件、旧日志，回收磁盘空间 |
| `service_restart` | 优雅重启失败的服务 |
| `memory_pressure` | 安全杀死内存占用过高的进程 |
| `log_rotation` | 轮转和压缩过大的日志文件 |
| `zombie_killer` | 终止僵尸进程 |
| `connection_reset` | 重置卡住的网络连接 |
| `cpu_high` | CPU 使用率过高排查和定位 |
| `docker_cleanup` | Docker 资源清理（停止容器、悬空镜像） |
| `network_diag` | 网络连通性诊断（DNS、路由、端口） |
| `mysql_health` | MySQL 健康检查与连接管理 |
| `redis_health` | Redis 健康检查与内存管理 |
| `nginx_fix` | Nginx 排查修复（配置检测、日志分析） |
| `swap_pressure` | Swap 使用率过高排查 |

**AI 生成 Runbook**: 用自然语言描述运维场景，AI 自动生成可执行的 Runbook 并进行安全检查 — 通过 `/api/v1/ai/generate-runbook` 接口。

---

## 我们解决的问题

- **告警疲劳**: Prometheus每天发200+条告警，80%是误报
- **响应缓慢**: 凌晨3点叫醒值班工程师处理脚本就能解决的问题
- **工具昂贵**: 企业监控工具年费10万+，但还是需要人工处理
- **缺乏上下文**: "磁盘满了"告警，但不知道根因和解决方案

**监控行业的现实**: 大多数工具擅长 *发现* 问题但不擅长 *解决* 问题。NightMend 不是增加告警噪音——而是 **减少** 它。

---

## 完整安装指南

### 系统要求

- Docker 20+ & Docker Compose v2+
- 4核CPU / 8GB内存（初始构建；运行期2GB）
- 端口 3001（前端）& 8001（后端）可用

### 生产环境部署

```bash
# 1. 克隆到服务器
git clone https://github.com/LinChuang2008/nightmend.git /opt/nightmend
cd /opt/nightmend

# 2. 配置密钥（必须）
cp .env.example .env
# 生产前必须修改：
#   POSTGRES_PASSWORD  — 强密码
#   JWT_SECRET_KEY     — 随机字符串（生成: openssl rand -hex 32）
#   AI_API_KEY         — 你的DeepSeek API Key
#   AI_AUTO_SCAN=true  — 启用自动告警分析

# 3. 部署
docker compose up -d

# 4. 验证
curl http://localhost:8001/health
# {"status": "healthy"}
```

### 环境变量

| 变量 | 必需 | 说明 | 示例 |
|------|------|------|------|
| `POSTGRES_PASSWORD` | 是 | 数据库密码 | 强随机密码 |
| `JWT_SECRET_KEY` | 是 | JWT签名密钥 | `openssl rand -hex 32` |
| `AI_API_KEY` | 是 | DeepSeek API Key | `sk-abc123...` |
| `AI_AUTO_SCAN` | 推荐 | 自动分析告警 | `true` |
| `AGENT_ENABLED` | 可选 | 启用自动修复 | `false`（安全起见） |
| `AGENT_TOKEN_HMAC_KEY` | 生产必需 | Agent Token 签名密钥 | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |

---

## Agent — 跨平台监控客户端

NightMend Agent 采集系统指标、自动发现服务、监控数据库，支持 **Linux**、**Windows/Windows Server** 和 **macOS**。

**Linux:**
```bash
pip install nightmend-agent
nightmend-agent run -c /etc/nightmend/agent.yaml
```

**Windows (PowerShell):**
```powershell
.\scripts\install-windows-agent.ps1 -ServerUrl "http://your-server:8001" -Token "your-token"
.\scripts\install-windows-service.ps1   # 注册为 Windows 服务
```

| 功能 | Linux | Windows | macOS |
|------|:-----:|:-------:|:-----:|
| CPU / 内存 / 磁盘 / 网络 | ✓ | ✓ | ✓ |
| Docker 服务发现 | ✓ | ✓ | ✓ |
| 宿主机服务发现 | ✓ (ss) | ✓ (netstat) | - |
| 数据库监控 | ✓ | ✓ | ✓ |
| 日志采集 | ✓ | ✓ | ✓ |

---

## MCP集成 — 全球开源首创！

NightMend 是 **世界第一个开源监控平台**，内置 **MCP（模型上下文协议）** 支持。你的AI编程助手（Claude Code, Cursor）可以直接从聊天界面查询实时生产数据。

在 `backend/.env` 中添加：

```env
NIGHTMEND_MCP_ENABLED=true
NIGHTMEND_MCP_HOST=0.0.0.0
NIGHTMEND_MCP_PORT=8003
NIGHTMEND_MCP_TOKEN=your-secret-token
```

### 可用MCP工具（共5个）

| 工具 | 功能 |
|------|------|
| `get_servers_health` | 获取所有监控服务器的实时健康状态 |
| `get_alerts` | 按状态、严重性、主机、时间范围查询告警 |
| `search_logs` | 按关键词和时间范围搜索生产日志 |
| `analyze_incident` | AI驱动的根因分析和修复建议 |
| `get_topology` | 检索服务依赖图数据 |

连接后，向你的AI助手询问：`"显示prod-server-01上的所有严重告警"` / `"分析昨晚CPU飙升事件"` / `"搜索过去2小时的OOM错误"`

---

## 文档

**给用户**
- [快速开始](docs/getting-started.md) — 5 分钟入门
- [用户手册 v1.1](docs/USER_MANUAL.md) — 菜单导览 · 常用场景 · 权限
- [用户指南（旧版）](docs/user-guide.md) — v1.0 参考

**给运维**
- [部署手册 v1.1](docs/DEPLOYMENT_MANUAL.md) — `deploy.sh` · 生产加固 · HTTPS · 备份
- [安装指南](docs/installation.md) — 详细 Docker Compose 手册
- [Agent 安装](docs/AGENT_INSTALL.md) — Linux / Windows / K8s / Ansible
- [Windows Agent](docs/windows-agent-install.md)

**给二开**
- [代码导览 Code Guide](docs/CODE_GUIDE.md) — 二开地图 · 扩展 walkthrough · 约定
- [系统架构](docs/architecture.md)
- [API 参考](docs/api-reference.md)
- [MCP 集成](docs/MCP_INTEGRATION.md)
- [Prometheus 对接](docs/prometheus-integration.md)
- [贡献指南](CONTRIBUTING.md) · [更新日志](CHANGELOG.md)

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | React 19, TypeScript, Vite, Ant Design 6, ECharts 6 |
| **后端** | Python 3.9+, FastAPI, SQLAlchemy, AsyncIO |
| **数据库** | PostgreSQL 15+, Redis 7+ |
| **AI** | DeepSeek API（可配置LLM端点） |
| **Agent** | Python 3.9+, psutil — 支持 Linux / Windows / macOS |
| **部署** | Docker Compose |

---

## 参与贡献

我们需要理解告警疲劳的贡献者。

```bash
cp .env.example .env
docker compose -f docker-compose.dev.yml up -d
pip install -r requirements-dev.txt
cd frontend && npm install
```

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

---

## 联系我们

- [GitHub Discussions](https://github.com/LinChuang2008/nightmend/discussions) — 提问、建议、交流
- [报告Bug](https://github.com/LinChuang2008/nightmend/issues/new)
- Email: [lchuangnet@lchuangnet.com](mailto:lchuangnet@lchuangnet.com)

---

<div align="center">

**[Apache 2.0](LICENSE)** — 使用、Fork、商用均可。

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>
