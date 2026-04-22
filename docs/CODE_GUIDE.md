# NightMend 二开导览（Code Guide）

> 版本 v1.1 · 更新 2026-04-23
> 目标：让新同学 1 小时内跑通本地环境 + 3 小时内能加一个接口 / 一个页面 / 一个采集器

---

## 一、架构全景

```
┌─────────────────────────────────────────────────────────────────┐
│                       用户 / 浏览器                                │
└─────────────────────┬───────────────────────────────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Frontend · React + TypeScript + Vite + Ant Design              │
│  frontend/src/  (105 tsx/ts · 23.7k 行)                         │
│     pages/        30 个页面（Dashboard / Hosts / Alerts …）      │
│     components/   共享组件 + AppLayout + AuthGuard              │
│     services/     axios 封装的 API client                        │
│     i18n/         zh.ts / en.ts                                  │
│     styles/       tokens.css（设计系统） + navigation.css        │
└─────────────────────┬───────────────────────────────────────────┘
                      │  HTTP(S) + WebSocket
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Backend · FastAPI + SQLAlchemy + Celery                        │
│  backend/app/  (196 py · 37.4k 行)                              │
│     main.py       FastAPI 应用入口 + 生命周期                    │
│     api/v1/       主 API 路由（REST）                            │
│     routers/      按功能划分的独立路由模块                        │
│     models/       SQLAlchemy ORM 模型                            │
│     schemas/      Pydantic 请求/响应 schema                       │
│     services/     业务逻辑（领域服务）                             │
│     core/         config + security + logging                    │
│     tasks/        后台定时任务 / Celery jobs                      │
│     mcp/          Model Context Protocol server                   │
│     remediation/  自动修复引擎                                     │
│     alert_sources/ 外部告警源（Prometheus / Alertmanager）        │
└──┬──────────┬──────────┬──────────┬─────────────────────────────┘
   │          │          │          │
   ▼          ▼          ▼          ▼
┌──────┐ ┌──────┐ ┌─────────┐ ┌──────────┐
│ PG   │ │Redis │ │Clickhouse│ │   Loki   │
└──────┘ └──────┘ └─────────┘ └──────────┘
   元数据  队列+缓存   指标 OLAP     日志

                      ▲
                      │  HTTP 上报 + JWT
┌─────────────────────┴───────────────────────────────────────────┐
│  Agent · Python (pyproject + uv)                                │
│  agent/nightmend_agent/                                         │
│     __main__.py     启动 + 配置加载                              │
│     service/         上报客户端 / 心跳 / 自升级                   │
│     db_collectors/   PG / MySQL / Redis 采集器                    │
│     collectors/      CPU / MEM / DISK / NET / GPU / journald     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、仓库目录

```
vigilops/
├── agent/              Agent Python 源 + install-agent-centos7.sh
├── backend/            FastAPI + alembic
│   └── app/
│       ├── main.py     应用入口（lifespan + middleware）
│       ├── core/       config.py · security.py · logging.py
│       ├── api/v1/     主 REST 路由总装
│       ├── routers/    按功能模块拆的路由（30+ 文件）
│       ├── models/     ORM
│       ├── schemas/    Pydantic
│       ├── services/   业务逻辑
│       ├── tasks/      后台作业
│       ├── mcp/        MCP server
│       ├── remediation/ AI 修复引擎
│       └── alert_sources/ 外部告警 adapter
├── frontend/
│   └── src/
│       ├── App.tsx     根组件 + 路由表（30 Route）
│       ├── main.tsx    挂载入口
│       ├── pages/      页面（懒加载 30 个）
│       ├── components/ 共享组件 + AppLayout + AuthGuard
│       ├── services/   axios API client
│       ├── contexts/   React Context（Theme 等）
│       ├── hooks/      自定义 hooks
│       ├── i18n/       多语言
│       ├── styles/     tokens.css + navigation.css
│       └── utils/      统一工具
├── docs/               文档（用户/部署/Agent/本文等）
├── docker-compose.yml  7 服务 · 主 compose
├── docker-compose.ssl.yml  HTTPS 叠加
├── docker-compose.prod.yml 生产资源限制
├── deploy.sh           一键部署（零交互）
├── install.sh          交互式引导安装
├── quickstart.sh       5 分钟体验
└── scripts/            CI / 运维脚本
```

---

## 三、本地开发启动

### 后端

```bash
cd backend
pip install -e .               # 或 uv pip install -e .

cp ../.env.example .env
# 至少设置：DATABASE_URL / REDIS_URL / ENVIRONMENT=development

cd .. && docker compose up -d postgres redis clickhouse loki

cd backend && alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

API 文档自动生成：`http://localhost:8000/docs`

### 前端

```bash
cd frontend
npm install
npm run dev       # Vite dev server :5173
```

Vite 已配 `/api → localhost:8000` 代理（`vite.config.ts`）。

### Agent（本地联调）

```bash
cd agent
pip install -e .
cp agent.example.yaml /tmp/agent.yaml
# 编辑 server.url / token
nightmend-agent --config /tmp/agent.yaml --log-level debug
```

---

## 四、扩展 Walkthrough

### 场景 A · 加一个新后端 API

需求：新增 `GET /api/v1/widgets` 返回 widget 列表。

1. **Model** · `backend/app/models/widget.py`
   ```python
   from sqlalchemy import Column, Integer, String, DateTime, func
   from app.db.base import Base

   class Widget(Base):
       __tablename__ = "widgets"
       id = Column(Integer, primary_key=True)
       name = Column(String(64), nullable=False)
       created_at = Column(DateTime, server_default=func.now())
   ```
2. **Schema** · `backend/app/schemas/widget.py`
   ```python
   from pydantic import BaseModel
   class WidgetOut(BaseModel):
       id: int
       name: str
       class Config:
           from_attributes = True
   ```
3. **Service**（复杂业务才拆）· `backend/app/services/widget_service.py`
4. **Router** · `backend/app/routers/widgets.py`
   ```python
   from fastapi import APIRouter, Depends
   from app.db.session import get_db
   from app.models.widget import Widget
   from app.schemas.widget import WidgetOut

   router = APIRouter(prefix="/widgets", tags=["widgets"])

   @router.get("", response_model=list[WidgetOut])
   def list_widgets(db=Depends(get_db)):
       return db.query(Widget).all()
   ```
5. **注册总路由** · `backend/app/api/v1/__init__.py`
   ```python
   from app.routers import widgets
   api_router.include_router(widgets.router)
   ```
6. **Migration**
   ```bash
   alembic revision --autogenerate -m "add widgets"
   alembic upgrade head
   ```
7. **测试**
   ```bash
   pytest backend/tests/routers/test_widgets.py -v
   ```

### 场景 B · 加一个前端新页

需求：新增 `/widgets` 页面展示列表。

1. **Service 层** · `frontend/src/services/widgets.ts`
   ```ts
   import api from './api';
   export interface Widget { id: number; name: string; }
   export const widgetService = {
     list: () => api.get<{ items: Widget[] }>('/widgets'),
   };
   ```
2. **Page** · `frontend/src/pages/Widgets.tsx`（参考 `HostList.tsx` 结构）
3. **路由注册** · `frontend/src/App.tsx`
   ```tsx
   const Widgets = lazy(() => import('./pages/Widgets'));
   // Routes 里：
   <Route path="/widgets" element={<Widgets />} />
   ```
4. **菜单项** · `frontend/src/components/AppLayout.tsx`（合适的分组）
   ```tsx
   { key: '/widgets', icon: <AppstoreOutlined />, label: t('menu.widgets') }
   ```
5. **i18n** · `frontend/src/i18n/locales/zh.ts` + `en.ts`
   ```ts
   menu: { widgets: '小组件' },
   widgets: { title: '小组件列表' },
   ```

### 场景 C · 加一个 Agent 采集器

需求：采集 `nvidia-smi` 的 GPU 指标。

1. **采集器模块** · `agent/nightmend_agent/collectors/gpu.py`
   ```python
   import subprocess
   def collect_gpu():
       try:
           out = subprocess.check_output(
               ["nvidia-smi",
                "--query-gpu=index,utilization.gpu,memory.used,memory.total,"
                "temperature.gpu,power.draw",
                "--format=csv,noheader,nounits"], timeout=3, text=True)
           gpus = []
           for line in out.strip().splitlines():
               idx, util, mem_used, mem_total, temp, power = [x.strip() for x in line.split(",")]
               gpus.append({
                   "index": int(idx),
                   "sm_util": float(util),
                   "vram_used_mb": float(mem_used),
                   "vram_total_mb": float(mem_total),
                   "temp_c": float(temp),
                   "power_w": float(power),
               })
           return gpus
       except Exception:
           return []
   ```
2. **注册** · `agent/nightmend_agent/__main__.py` 采集循环：
   ```python
   from .collectors import gpu
   payload["gpu"] = gpu.collect_gpu()
   ```
3. **上报 schema** · 与后端约定 `/api/v1/agents/metrics` 接受 `gpu: [...]`
4. **后端存储** · `backend/app/models/host_metrics.py` 加 GPU 字段
5. **前端展示** · 主机详情页消费新字段

---

## 五、关键约定

### 代码风格

- **TS/TSX**：ESLint + Prettier（`frontend/.eslintrc`）
  - Props 用 `interface`
  - 函数组件 + hooks
  - 不用 `any`；外部数据用 `unknown` 再 narrow
- **Python**：ruff + black（`backend/pyproject.toml`）
  - 类型注解 PEP 484
  - docstring 中英双语（`main.py` 是样板）
- **Shell**：shellcheck · `set -euo pipefail`

### i18n

- 所有用户可见文案走 `t('key')`
- Key 放对应 namespace（`alerts.severity` / `hosts.online`）
- zh + en 同步加（漏加 en 会 fallback 回 key）
- 带占位符用 `t('common.total', { count: total })`

### 错误处理

- 后端：抛 `HTTPException` 或自定义 `BusinessError` · 不要裸 `raise Exception`
- 前端：`try/catch` + `message.error(...)` 或 `ErrorState` 组件
- Never silently swallow：`console.warn` / `logger.error` 至少留痕

### 权限

- Admin / Operator / Viewer · 见 `backend/app/core/security.py`
- 每个 router 函数 `Depends(require_role("admin"))`
- 前端 `AuthGuard` + `useCurrentUser()` 检查

### 数据库 migration

- 改 model 后务必 `alembic revision --autogenerate -m "xxx"`
- **禁止**手改历史 migration · 新增 revision 回滚
- 生产 `deploy.sh --upgrade` 自动 `alembic upgrade head`

---

## 六、调试 / 测试

### 后端

```bash
pytest backend/tests/ -v                                # 全量
pytest backend/tests/routers/test_hosts.py::test_list_hosts -v   # 单测
pytest --cov=app --cov-report=term-missing              # 覆盖率

# 本地 debug
pip install ipdb
# 代码里：import ipdb; ipdb.set_trace()
```

### 前端

```bash
cd frontend
npm run lint
npm run build       # tsc -b + vite build · catch 类型错
npx playwright test # e2e
```

### API 联调

- Swagger UI: `http://localhost:8000/docs`
- ReDoc:      `http://localhost:8000/redoc`
- 直连 DB:    `docker compose exec postgres psql -U nightmend -d nightmend`

### 前端 Docker 热构建

```bash
docker compose build frontend
docker compose up -d --force-recreate frontend
```

---

## 七、常见"为什么这样写"

| 疑问 | 答案 |
| --- | --- |
| 为什么用 lazy import 所有页面？ | 首屏 bundle 体积 · Vite 做 code-split |
| 为什么 tokens.css 用 `--nm-*` 前缀？ | 避免与 Ant 的 `--ant-*` token 冲突 |
| 告警规则同时在 model 和 alert engine？ | model 是数据层 · engine 是评估层 · 职责分离 |
| 为什么 agent 用 pipx 而不是系统 pip？ | 隔离依赖 · 升级不污染系统 Python |
| 为什么 ClickHouse 存指标，PG 存元数据？ | CH 时序聚合快 100 倍 · PG 关系查询友好 |
| 前端不用 Redux？ | 服务端状态用 axios + React Query（未来）· 组件状态足够 |

---

## 八、Onboarding Checklist

新同学接手时过一遍：

- [ ] `docs/USER_MANUAL.md` 过一遍产品形态
- [ ] `docs/architecture.md` 理解系统依赖
- [ ] 本文 § 三 启动本地环境（后端 + 前端 + agent）
- [ ] 登录 `demo@vigilops.io` / `demo123` 点完所有菜单
- [ ] 跑通一次 § 四 场景 A 加一个 hello API
- [ ] 跑通一次 § 四 场景 B 加一个空白页
- [ ] 读 `backend/app/main.py` 头部 docstring
- [ ] 读 `frontend/src/App.tsx`
- [ ] 跑 `pytest` + `npm run build` 全绿
- [ ] 开一个 MR 练手（例如补一个小文档）

---

## 九、相关文档

- 《用户手册》`docs/USER_MANUAL.md`
- 《部署手册》`docs/DEPLOYMENT_MANUAL.md`
- 《Agent 安装》`docs/AGENT_INSTALL.md`
- 《架构概览》`docs/architecture.md`
- 《API 参考》`docs/api-reference.md`
- 《MCP 集成》`docs/MCP_INTEGRATION.md`
- 《DESIGN.md》设计系统规范
- 《CONTRIBUTING.md》贡献流程
