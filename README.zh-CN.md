<div align="center">

# VigilOps

**你的团队每天收到 200+ 条告警，80% 是噪音。AI 在你睡觉时帮你修好。**

[![Stars](https://img.shields.io/github/stars/LinChuang2008/vigilops?style=for-the-badge&logo=github&color=gold)](https://github.com/LinChuang2008/vigilops)
[![Demo](https://img.shields.io/badge/Live_Demo-Try_Now-brightgreen?style=for-the-badge)](https://demo.lchuangnet.com/login)
[![Version](https://img.shields.io/badge/version-v2026.03.14-blue?style=for-the-badge)](https://github.com/LinChuang2008/vigilops/releases)
[![CI](https://img.shields.io/github/actions/workflow/status/LinChuang2008/vigilops/test.yml?branch=main&style=for-the-badge&label=CI)](https://github.com/LinChuang2008/vigilops/actions/workflows/test.yml)

[Live Demo](https://demo.lchuangnet.com/login) | [English](README.md) | [安装指南](#-本地部署5分钟) | [文档](#-文档)

<br/>

![VigilOps 演示 — 告警 → AI分析 → 自动修复 47秒](docs/screenshots/demo-animation.svg)

</div>

---

## 5分钟快速体验

### 在线演示（免安装）

> **官方演示**: [**demo.lchuangnet.com**](https://demo.lchuangnet.com/login)
> **登录账号**: `demo@vigilops.io` / `demo123` _(只读模式)_
> **立即查看**: AI告警分析、自动修复、MCP集成

### 本地部署（5分钟）

```bash
# 1. 克隆并配置
git clone https://github.com/LinChuang2008/vigilops.git && cd vigilops
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

## VigilOps 的独特之处

你试过 **Grafana + Prometheus**，知道 **夜莺** 和 **Datadog**。它们都能告诉你 *哪里出了问题*，但没有一个能 **帮你修好**。

VigilOps 是 **全球首个开源AI运维平台**，不只是监控——还能 **自愈**：

1. **AI分析** — DeepSeek 读取日志、指标、拓扑找到真正原因
2. **AI决策** — 从6个内置自动修复脚本中选择正确的Runbook
3. **AI修复** — 带安全检查和审批流程的自动执行
4. **AI学习** — 同类问题下次解决得更快

**全球首创**: VigilOps 是 **全世界第一个开源监控平台，内置 MCP（模型上下文协议）集成** — 你的AI编程助手可以直接查询生产环境数据。

---

## 功能对比（实话实说）

| **功能** | **VigilOps** | **夜莺** | **Prometheus+Grafana** | **Datadog** | **Zabbix** |
|---|:---:|:---:|:---:|:---:|:---:|
| **AI根因分析** | Built-in | - | - | Enterprise | - |
| **自动修复** | 6 Runbooks | - | - | Enterprise | - |
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

**6个内置Runbook** — 生产可用：

| Runbook | 解决什么 |
|---------|----------|
| `disk_cleanup` | 清理临时文件、旧日志，回收磁盘空间 |
| `service_restart` | 优雅重启失败的服务 |
| `memory_pressure` | 安全杀死内存占用过高的进程 |
| `log_rotation` | 轮转和压缩过大的日志文件 |
| `zombie_killer` | 终止僵尸进程 |
| `connection_reset` | 重置卡住的网络连接 |

---

## 我们解决的问题

- **告警疲劳**: Prometheus每天发200+条告警，80%是误报
- **响应缓慢**: 凌晨3点叫醒值班工程师处理脚本就能解决的问题
- **工具昂贵**: 企业监控工具年费10万+，但还是需要人工处理
- **缺乏上下文**: "磁盘满了"告警，但不知道根因和解决方案

**监控行业的现实**: 大多数工具擅长 *发现* 问题但不擅长 *解决* 问题。VigilOps 不是增加告警噪音——而是 **减少** 它。

---

## 完整安装指南

### 系统要求

- Docker 20+ & Docker Compose v2+
- 4核CPU / 8GB内存（初始构建；运行期2GB）
- 端口 3001（前端）& 8001（后端）可用

### 生产环境部署

```bash
# 1. 克隆到服务器
git clone https://github.com/LinChuang2008/vigilops.git /opt/vigilops
cd /opt/vigilops

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

---

## MCP集成 — 全球开源首创！

VigilOps 是 **世界第一个开源监控平台**，内置 **MCP（模型上下文协议）** 支持。你的AI编程助手（Claude Code, Cursor）可以直接从聊天界面查询实时生产数据。

在 `backend/.env` 中添加：

```env
VIGILOPS_MCP_ENABLED=true
VIGILOPS_MCP_HOST=0.0.0.0
VIGILOPS_MCP_PORT=8003
VIGILOPS_MCP_TOKEN=your-secret-token
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

| 指南 | 说明 |
|------|------|
| [快速开始](docs/getting-started.md) | 首次安装指南 |
| [安装指南](docs/installation.md) | Docker/手动部署 + 环境配置 |
| [用户手册](docs/user-guide.md) | 完整功能说明 |
| [API参考](docs/api-reference.md) | REST API 文档 |
| [系统架构](docs/architecture.md) | 系统设计 + 数据流 |
| [贡献指南](docs/contributing.md) | 开发环境 + 规范 |

---

## 技术栈

| 层级 | 技术 |
|------|------|
| **前端** | React 19, TypeScript, Vite, Ant Design 6, ECharts 6 |
| **后端** | Python 3.9+, FastAPI, SQLAlchemy, AsyncIO |
| **数据库** | PostgreSQL 15+, Redis 7+ |
| **AI** | DeepSeek API（可配置LLM端点） |
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

- [GitHub Discussions](https://github.com/LinChuang2008/vigilops/discussions) — 提问、建议、交流
- [报告Bug](https://github.com/LinChuang2008/vigilops/issues/new)
- Email: [lchuangnet@lchuangnet.com](mailto:lchuangnet@lchuangnet.com)

---

<div align="center">

**[Apache 2.0](LICENSE)** — 使用、Fork、商用均可。

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

</div>
