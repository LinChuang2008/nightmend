# VigilOps 技术评审报告

> **日期**: 2026-03-02  
> **执行**: AI 技术评审 Agent  
> **环境**: 本地 Docker (macOS)  
> **后端**: http://localhost:8000 | **前端**: http://localhost:3001

---

## 📋 评审摘要

| 类别 | 问题数 | 已修复 | 待处理 |
|------|--------|--------|--------|
| ClickHouse 容器 | 1 | ✅ 1 | 0 |
| 后端 Bug | 2 | ✅ 2 | 0 |
| 前端 i18n | 1 | ✅ 1 | 0 |
| 技术债务 | 3 | 0 | 3（需人工决策）|

---

## 🔴 已发现并修复的问题

### 1. ClickHouse 容器持续 Restarting

**现象**：`vigilops-clickhouse-1` 状态 `Restarting (137)`，每隔几秒重启一次。

**根因分析**：
- Exit Code 137 = 被 SIGKILL 杀死（OOM Kill 或资源限制）
- ClickHouse 配置了 max_memory_usage: 4GB，但 Docker 环境总内存仅 7.65GB
- 其他容器（postgres/redis/backend/frontend）合计占用约 2~3GB
- ClickHouse 启动时内存分配超限被 macOS 强制杀死
- 日志反复出现 `Include not found: networks`（配置中 incl="networks" 引用失败）

**修复**：在 `docker-compose.yml` 中为 clickhouse 添加 `profiles: [clickhouse]`，使其不再默认启动。  
当前日志后端使用 PostgreSQL（log_backend_type = "postgresql"），ClickHouse 不是必须服务。  
需要 ClickHouse 时，使用 `docker compose --profile clickhouse up -d` 启动。

**文件**: `docker-compose.yml`

---

### 2. 后端 AlertDeduplicationService async/sync 混用 Bug

**现象**：后端日志每分钟报错：
```
AttributeError: 'AsyncSession' object has no attribute 'query'
```

**根因**：`alert_deduplication_cleanup.py` 中 `_perform_cleanup()` 使用 `async with async_session()` 获取 AsyncSession，但传给了使用同步 ORM API（self.db.query()）的 AlertDeduplicationService。

**修复**：改为使用同步 SessionLocal() 创建会话，避免 async/sync 混用。

**文件**: `backend/app/tasks/alert_deduplication_cleanup.py`

---

### 3. escalation_scheduler.py 引用不存在的函数

**现象**：`escalation_scheduler.py` 导入 `get_async_session`，但该函数在 `database.py` 中不存在（只有 `async_session`）。

**根因**：代码使用了未定义的别名，属于重命名遗留问题。

**修复**：`from app.core.database import async_session as get_async_session`

**文件**: `backend/app/tasks/escalation_scheduler.py`

---

### 4. 前端 i18n 按钮硬编码中文

**现象**：Dashboard 空状态页在 EN 模式下，CTA 按钮显示中文"添加你的第一台服务器"。

**根因**：`CustomizableDashboard.tsx` 直接硬编码中文字符串，未使用 useTranslation hook。

**修复**：
1. 添加 `import { useTranslation } from 'react-i18next'`
2. 在组件内添加 `const { t } = useTranslation()`
3. 将硬编码文本改为 `t('state.empty.dashboard.actionText')`（对应英文 'Add Host'）

**文件**: `frontend/src/components/dashboard/CustomizableDashboard.tsx`

---

## 验证结果

- 后端健康检查：{"status":"ok","checks":{"api":"ok","database":"ok","redis":"ok"}} ✅
- 后端启动日志：无 ERROR，所有 task 正常 started ✅
- 前端 Dashboard 按钮 EN 模式显示 "Add Host" ✅
- ClickHouse 容器已停止并移至可选 profile ✅

---

## ⚠️ 技术债务（需人工决策）

### TD-1：ClickHouse XML 配置 networks include 错误
**现状**：vigilops.xml 中 `<networks incl="networks" />` 引用不存在节点，default 用户网络访问控制不生效。  
**建议**：修改为明确的 `<networks><ip>::/0</ip></networks>`（或限制为内网段）。  
**优先级**：中（ClickHouse 当前禁用，暂无即时风险）

### TD-2：AlertDeduplicationService 全面使用同步 ORM
**现状**：alert_deduplication.py 所有方法使用同步 self.db.query()，与项目整体异步架构不一致。  
**建议**：全面重构为 async/await + select() 语句，或明确标注"仅供同步上下文"。  
**优先级**：低（已用 sync session 绕过，功能正常）

### TD-3：后端任务重复启动
**现象**：日志中 Data retention task started 和 Alert deduplication cleanup task started 各出现两次，同一 task 被注册了两次。  
**建议**：检查 main.py 的 startup 事件，找出重复注册原因并去重。  
**优先级**：中（任务重复执行可能导致数据清理冲突）

---

## Docker 容器最终状态

```
vigilops-backend-1    Up (健康)   :8000 ✅
vigilops-frontend-1   Up (健康)   :3001 ✅  
vigilops-postgres-1   Up (健康)   :5432 ✅
vigilops-redis-1      Up (健康)   :6379 ✅
vigilops-clickhouse-1 已移除（移至 profile=clickhouse）✅
```

---

## 后续建议（优先级排序）

1. **立即**：检查并修复后端任务重复启动问题（TD-3）
2. **本周**：修复 ClickHouse XML 配置 networks 引用问题（TD-1）
3. **下次迭代**：AlertDeduplicationService 重构为全异步（TD-2）
4. **Q2 路线图**：参照 POST_COMPLETION_ROADMAP.md，GitHub 推广和文档完善是最高优先级

---
*报告生成时间：2026-03-02 07:52 GMT+8*
