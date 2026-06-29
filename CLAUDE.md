# NightMend — Project Instructions

## Design System
Always read DESIGN.md before making any visual or UI decisions.
All font choices, colors, spacing, and aesthetic direction are defined there.
Do not deviate without explicit user approval.
In QA mode, flag any code that doesn't match DESIGN.md.

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming → invoke office-hours
- Bugs, errors, "why is this broken", 500 errors → invoke investigate
- Ship, deploy, push, create PR → invoke ship
- QA, test the site, find bugs → invoke qa
- Code review, check my diff → invoke review
- Update docs after shipping → invoke document-release
- Weekly retro → invoke retro
- Design system, brand → invoke design-consultation
- Visual audit, design polish → invoke design-review
- Architecture review → invoke plan-eng-review
- Save progress, checkpoint, resume → invoke checkpoint
- Code quality, health check → invoke health

## Overview
NightMend (vigilops) — AI 驱动的智能运维监控平台。接收告警 → AI 分析 → 自动修复。

## Tech Stack
- **后端**: Python 3, FastAPI, SQLAlchemy (async), PostgreSQL, Redis, Alembic migrations
- **前端**: React 19, TypeScript, Vite 7, Ant Design 6, ECharts, i18n
- **Agent**: Python, asyncssh, 独立部署到被监控主机
- **部署**: Docker Compose (dev/demo/prod/ssl 四套), ClickHouse (时序数据)
- **AI**: DeepSeek API, MCP 集成, fastmcp

## Project Structure
```
vigilops/
├── backend/              # FastAPI 后端
│   ├── app/
│   │   ├── api/          # REST API 路由
│   │   ├── models/       # SQLAlchemy 模型
│   │   ├── services/     # 业务逻辑
│   │   ├── remediation/  # 自动修复引擎
│   │   ├── mcp/          # MCP 集成
│   │   └── tasks/        # 后台任务
│   ├── alembic/          # 数据库迁移
│   └── tests/            # 后端测试
├── frontend/             # React 前端
│   └── src/
│       ├── pages/        # 页面
│       ├── components/   # 组件
│       ├── services/     # API 调用
│       └── stores/       # 状态管理
├── agent/                # 被监控主机 Agent
│   └── nightmend_agent/  # Agent 核心代码
├── charts/               # Helm charts
├── deploy/               # 部署脚本
└── docker-compose*.yml   # 多环境部署
```

## Development

### Common Commands
- **后端开发**: `cd backend && uvicorn app.main:app --reload`
- **后端测试**: `cd backend && pytest`
- **前端开发**: `cd frontend && npm run dev`
- **前端构建**: `cd frontend && tsc -b && npm run build`
- **前端 lint**: `cd frontend && npm run lint`
- **全栈部署**: `docker compose up -d --build`
- **Demo 模式**: `docker compose -f docker-compose.demo.yml up -d`
- **DB 迁移**: `cd backend && alembic upgrade head`

### Branch Strategy
- Main branch: `main`
- Feature: `feat/[description]`
- Fix: `fix/[description]`
- Commit format: conventional commits (`feat:`, `fix:`, `chore:`)

## Rules
- 数据库变更必须通过 Alembic migration，不要手动改表
- 前端有 i18n 支持，新增文案必须同时加中英文 key
- Agent 模块独立部署，修改时注意向下兼容
- Docker Compose 有四套配置 (dev/demo/prod/ssl)，改一个要检查是否影响其他
- AI/MCP 相关代码修改后，确认 fastmcp 接口兼容性

## Health Stack

- typecheck: cd frontend && npx tsc --noEmit
- lint_fe: cd frontend && npx eslint .
- lint_be: /usr/local/Cellar/pyenv/versions/3.12.12/bin/ruff check . --exclude ".git,node_modules,frontend/node_modules,.venv,venv,__pycache__"
- test: cd backend && /usr/local/Cellar/pyenv/versions/3.12.12/bin/python -m pytest --tb=short -q
- deadcode: cd frontend && npx knip
- shell: find . -name "*.sh" -not -path "./.git/*" -not -path "*/node_modules/*" -exec shellcheck {} \;

## Workflow
默认档位: **M** — 产品迭代期，多为中等功能开发和 bug 修复。
紧急 bug (P0/P1) 用 S 档：`/investigate` → 修复 → `/review` → `/ship`
新大功能 (如新告警源接入) 用 L 档：`/autoplan` → 开发 → `/qa` → `/cso` → `/ship`
使用 `/workflow [任务描述]` 获取具体路由建议。
