# VigilOps 数据库初始化脚本

## 概述

本目录包含 VigilOps 项目的完整数据库初始化脚本，基于生产环境实际表结构生成。

## 文件说明

### `init_complete.sql`
完整的数据库初始化脚本，包含所有 37 张表的定义和默认数据。

## 执行方式

### 方式一：通过 Docker Compose 执行（推荐）

```bash
# 在项目根目录执行
docker compose exec -T postgres psql -U vigilops -d vigilops -f backend/sql/init_complete.sql
```

### 方式二：直接连接 PostgreSQL 执行

```bash
psql -h localhost -U vigilops -d vigilops -f backend/sql/init_complete.sql
```

### 方式三：在生产服务器上执行

```bash
cd /docker/vigilops
docker compose exec -T postgres psql -U vigilops -d vigilops -f - < backend/sql/init_complete.sql
```

## 表结构分类

### 核心功能表 (4 张)
- `users` - 用户表
- `agent_tokens` - Agent 令牌
- `settings` - 系统配置
- `audit_logs` - 审计日志

### 监控数据表 (8 张)
- `hosts` - 主机表
- `host_metrics` - 主机指标
- `services` - 服务表
- `service_checks` - 服务检查记录
- `log_entries` - 日志采集
- `monitored_databases` - 数据库监控
- `db_metrics` - 数据库指标
- `servers` - 多服务器拓扑

### 告警系统表 (8 张)
- `alert_rules` - 告警规则
- `alerts` - 告警记录
- `alert_groups` - 告警聚合
- `alert_deduplications` - 告警去重
- `escalation_rules` - 升级规则
- `alert_escalations` - 告警升级记录
- `on_call_groups` - 值班组
- `on_call_schedules` - 值班排期

### 通知系统表 (3 张)
- `notification_channels` - 通知渠道
- `notification_logs` - 通知日志
- `notification_templates` - 通知模板

### 服务拓扑表 (5 张)
- `service_dependencies` - 服务依赖
- `topology_layouts` - 拓扑布局
- `service_groups` - 服务分组
- `server_services` - 服务器服务关联
- `nginx_upstreams` - Nginx 上游

### SLA 管理表 (2 张)
- `sla_rules` - SLA 规则
- `sla_violations` - SLA 违规记录

### AI 功能表 (3 张)
- `ai_insights` - AI 分析结果
- `remediation_logs` - 自动修复日志
- `ai_feedback` - AI 反馈
- `ai_feedback_summary` - AI 反馈汇总

### 报告和仪表盘表 (2 张)
- `reports` - 运维报告
- `dashboard_components` - 仪表盘组件
- `dashboard_layouts` - 仪表盘布局

## 与项目迁移文件的关系

本脚本整合了以下目录中的所有迁移：

1. **`backend/migrations/*.sql`** - 23 个 SQL 迁移文件
2. **`backend/alembic/versions/*.sql`** - Alembic SQL 迁移文件

主要差异（服务器上有但项目中缺失）：

1. **`alert_groups` 表** - 完全缺失，已添加
2. **`agent_tokens` 表字段** - 服务器有 `token_hash`, `token_prefix`, `created_by`
3. **`alerts` 表字段** - 服务器有 `title`, `title_en`, `fired_at`, `escalation_level` 等
4. **`alert_rules` 表字段** - 服务器有 `name_en`, `rule_type`, `notification_channel_ids`, `continuous_alert` 等
5. **`hosts` 表字段** - 服务器有 `display_name`, `private_ip`, `public_ip`, `network_info`
6. **`host_metrics` 表字段** - 字段名称和时间戳字段不一致

## 注意事项

1. **数据备份**：执行前请备份现有数据库
2. **幂等性**：脚本使用 `IF NOT EXISTS`，可重复执行
3. **外键依赖**：表按依赖顺序创建，无需手动处理
4. **默认数据**：包含 8 个预置仪表盘组件

## 验证安装

执行后可验证表数量：

```sql
SELECT COUNT(*) AS table_count
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
-- 预期结果: 37
```

## 查看表结构

```sql
\d+ table_name
-- 例如: \d+ alerts
```

## 更新日志

- **2026-03-13** - 初始版本，基于生产环境数据库结构生成
