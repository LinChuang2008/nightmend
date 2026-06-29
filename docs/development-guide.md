# 贡献指南（详细版）

> 本文档是 [根目录 CONTRIBUTING.md](../CONTRIBUTING.md) 的详细补充。基础的 PR 流程、Commit 规范等请先阅读根目录版本。

## 目录

- [开发环境搭建](#开发环境搭建)
- [项目结构](#项目结构)
  - [后端目录结构](#后端目录结构)
  - [前端目录结构](#前端目录结构)
- [API 开发流程](#api-开发流程)
- [代码规范](#代码规范)
- [测试要求](#测试要求)
- [提交与发布](#提交与发布)

---

## 开发环境搭建

### 前置条件

| 工具 | 最低版本 |
|------|---------|
| Python | 3.11+ |
| Node.js | 18+ |
| Docker & Docker Compose | 最新稳定版 |
| PostgreSQL | 15+（或使用 Docker） |
| Redis | 7+（或使用 Docker） |
| Git | 2.30+ |

### 第一步：克隆仓库

```bash
git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend
```

### 第二步：启动基础设施

```bash
# 使用 Docker 启动 PostgreSQL 和 Redis
docker compose -f docker-compose.dev.yml up -d postgres redis
```

### 第三步：启动后端

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements-dev.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env，填写数据库连接、AI_API_KEY 等

# 启动开发服务器
uvicorn app.main:app --reload --port 8001
```

### 第四步：启动前端

```bash
cd frontend
npm install
npm run dev
# 默认访问 http://localhost:5173
```

### 第五步：验证

- 后端 API 文档：http://localhost:8001/docs
- 前端页面：http://localhost:5173
- 注册账号并登录

---

## 项目结构

### 后端目录结构

```
backend/app/
├── main.py                  # FastAPI 应用入口，注册所有 router
├── core/                    # 核心模块
│   ├── config.py            # 配置（从 .env 读取）
│   ├── database.py          # 数据库连接与会话
│   ├── security.py          # JWT、密码哈希、权限校验
│   └── deps.py              # 依赖注入（当前用户、数据库会话等）
├── models/                  # SQLAlchemy ORM 模型（20+ 个）
│   ├── user.py              # 用户模型（RBAC 角色）
│   ├── host.py              # 主机 & 主机指标
│   ├── alert.py             # 告警 & 告警规则
│   ├── service.py           # 服务 & 服务依赖
│   ├── log_entry.py         # 日志条目
│   ├── db_metric.py         # 数据库监控指标
│   ├── notification.py      # 通知 & 通知模板
│   ├── remediation_log.py   # 修复日志
│   ├── sla.py               # SLA 配置
│   └── ...
├── schemas/                 # Pydantic 请求/响应模型
│   ├── user.py
│   ├── host.py
│   ├── alert.py
│   └── ...
├── routers/                 # API 路由（24 个）
│   ├── auth.py              # 认证（注册/登录）
│   ├── users.py             # 用户管理
│   ├── hosts.py             # 主机管理
│   ├── alerts.py            # 告警管理
│   ├── alert_rules.py       # 告警规则
│   ├── ai_analysis.py       # AI 分析
│   ├── databases.py         # 数据库监控
│   ├── logs.py              # 日志管理
│   ├── topology.py          # 服务拓扑
│   ├── remediation.py       # 自动修复
│   ├── notifications.py     # 通知管理
│   ├── sla.py               # SLA 管理
│   ├── dashboard.py         # 仪表盘
│   ├── dashboard_ws.py      # 仪表盘 WebSocket
│   ├── agent.py             # Agent 数据上报
│   └── ...
├── services/                # 业务服务层（7 个）
│   ├── ai_engine.py         # AI 引擎（DeepSeek 集成）
│   ├── anomaly_scanner.py   # 异常扫描
│   ├── notifier.py          # 通知发送 + 降噪
│   ├── report_generator.py  # 报告生成
│   ├── memory_client.py     # 运维记忆系统
│   ├── alert_seed.py        # 告警种子数据
│   └── audit.py             # 审计服务
├── remediation/             # 自动修复子系统
│   ├── agent.py             # 修复 Agent 主控
│   ├── ai_client.py         # AI 诊断客户端
│   ├── command_executor.py  # 远程命令执行
│   ├── listener.py          # 告警监听触发
│   ├── runbook_registry.py  # Runbook 注册中心
│   ├── safety.py            # 安全检查 & 审批流
│   └── runbooks/            # 内置 Runbook（6 个）
│       ├── disk_cleanup.py
│       ├── memory_pressure.py
│       ├── service_restart.py
│       ├── log_rotation.py
│       ├── zombie_killer.py
│       └── connection_reset.py
└── tasks/                   # 后台任务
```

### 前端目录结构

```
frontend/src/
├── App.tsx                  # 路由配置
├── main.tsx                 # 入口
├── api/                     # API 请求封装
├── components/              # 公共组件
├── layouts/                 # 布局组件
├── hooks/                   # 自定义 Hooks
├── utils/                   # 工具函数
├── types/                   # TypeScript 类型定义
└── pages/                   # 页面组件（22 个）
    ├── Login.tsx            # 登录
    ├── Dashboard.tsx        # 仪表盘（WebSocket 实时推送）
    ├── HostList.tsx         # 服务器列表
    ├── HostDetail.tsx       # 服务器详情
    ├── ServiceList.tsx      # 服务列表
    ├── ServiceDetail.tsx    # 服务详情
    ├── Topology.tsx         # 服务拓扑图
    ├── topology/            # 拓扑图子组件
    ├── Logs.tsx             # 日志搜索 + 实时流
    ├── Databases.tsx        # 数据库监控列表
    ├── DatabaseDetail.tsx   # 数据库详情
    ├── AlertList.tsx        # 告警中心
    ├── AIAnalysis.tsx       # AI 分析
    ├── Remediation.tsx      # 自动修复管理
    ├── RemediationDetail.tsx# 修复详情
    ├── Reports.tsx          # 运维报告
    ├── SLA.tsx              # SLA 管理
    ├── NotificationChannels.tsx  # 通知渠道配置
    ├── NotificationLogs.tsx      # 通知日志
    ├── NotificationTemplates.tsx # 通知模板
    ├── AuditLogs.tsx        # 审计日志
    ├── Users.tsx            # 用户管理
    └── Settings.tsx         # 系统设置
```

---

## API 开发流程

添加一个新的 API 功能的标准步骤：

### 1. 定义数据模型 (`models/`)

```python
# backend/app/models/my_feature.py
from sqlalchemy import Column, Integer, String, DateTime
from app.core.database import Base

class MyFeature(Base):
    __tablename__ = "my_features"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # ...
```

### 2. 定义 Schema (`schemas/`)

```python
# backend/app/schemas/my_feature.py
from pydantic import BaseModel

class MyFeatureCreate(BaseModel):
    name: str

class MyFeatureResponse(BaseModel):
    id: int
    name: str

    class Config:
        from_attributes = True
```

### 3. 创建 Router (`routers/`)

```python
# backend/app/routers/my_feature.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.deps import get_db, get_current_user

router = APIRouter(prefix="/my-features", tags=["My Feature"])

@router.get("/", response_model=list[MyFeatureResponse])
async def list_features(db: Session = Depends(get_db)):
    # 实现逻辑
    ...
```

### 4. 注册到 `main.py`

```python
# backend/app/main.py
from app.routers import my_feature
app.include_router(my_feature.router, prefix="/api")
```

### 5. 数据库迁移

如果新增了模型，需要创建对应的数据库表（项目使用 SQLAlchemy 自动建表或手动 SQL）。

---

## 代码规范

### Python（后端）

| 项目 | 要求 |
|------|------|
| Linter & Formatter | **ruff** |
| 类型注解 | 所有函数参数和返回值必须有 Type Hints |
| 文档字符串 | 公开的 API 函数需写 docstring |
| 命名 | 变量/函数用 `snake_case`，类用 `PascalCase` |

```bash
# 检查
ruff check .

# 自动修复 + 格式化
ruff check --fix .
ruff format .
```

### TypeScript（前端）

| 项目 | 要求 |
|------|------|
| Linter | **ESLint** |
| Formatter | **Prettier** |
| 类型 | 避免 `any`，使用 `types/` 下的类型定义 |
| 组件 | 函数组件 + Hooks，不用 Class 组件 |

```bash
cd frontend

# Lint 检查
npm run lint

# 格式化
npm run format
```

### 通用规范

- 有意义的变量和函数命名，避免缩写
- 关键业务逻辑写注释
- 一个 PR 只做一件事
- Commit 遵循 [Conventional Commits](https://www.conventionalcommits.org/)

---

## 测试要求

### 后端测试

- 使用 **pytest** 编写测试
- 新增 API 需要对应的测试用例
- 测试文件放在 `backend/tests/` 目录下，命名 `test_*.py`
- 关键业务逻辑需有单元测试
- API 端点需有集成测试

```bash
# 运行全部测试
cd backend
pytest

# 运行指定测试
pytest tests/test_alerts.py -v

# 查看覆盖率
pytest --cov=app --cov-report=term-missing
```

### 前端测试

- 关键组件建议编写测试
- 运行 `npm run test`（如已配置）

### PR 合并前检查

- [ ] `ruff check .` 无错误
- [ ] `ruff format --check .` 无差异
- [ ] `pytest` 全部通过
- [ ] 前端 `npm run lint` 无错误
- [ ] 前端 `npm run build` 构建成功

---

## 提交与发布

### 分支规范

| 前缀 | 用途 | 示例 |
|------|------|------|
| `feat/` | 新功能 | `feat/sla-dashboard` |
| `fix/` | Bug 修复 | `fix/alert-duplicate` |
| `docs/` | 文档更新 | `docs/api-reference` |
| `refactor/` | 重构 | `refactor/notification-service` |
| `test/` | 测试 | `test/remediation-runbook` |

### Commit 消息格式

```
<type>(<scope>): <subject>

<body>

<footer>
```

示例：

```
feat(alerts): 添加告警规则批量启用/禁用

- 新增 PUT /api/alert-rules/batch-toggle 接口
- 前端告警规则页面添加批量操作按钮

Closes #123
```

---

> 有更多问题？查看 [FAQ](./faq.md) 或在 [GitHub Discussions](https://github.com/LinChuang2008/nightmend/discussions) 中提问。
