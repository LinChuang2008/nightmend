# DHH 工程师修复报告
> 日期：2026-03-02  
> 负责人：DHH（全栈工程师）  
> 目标：修复 P0 问题，让 Demo 体验打动用户

---

## 任务一：Demo 示例数据 ✅

### 问题
自动修复历史、告警升级记录等核心功能在 Demo 里没有数据，用户看不到产品最大卖点。

### 修复内容

**1. 新增种子脚本 `scripts/seed_demo_data.py`**
- 5 条自动修复执行记录（nginx reload、磁盘清理、服务重启、僵尸进程清理、DB 连接池重置）
- 3 条告警升级历史记录
- 1 条告警升级规则示例

**2. 修复 Alerts API 返回 `remediation_status` 字段**
- `backend/app/routers/alerts.py`：批量 join `remediation_logs` 表，返回每条告警的最新修复状态
- `backend/app/schemas/alert.py`：`AlertResponse` 新增 `remediation_status: Optional[str]` 字段

### 验证截图
- 自动修复页：5 条记录（4 条已完成 + 1 条失败）✅
- 告警中心修复状态列：已完成/失败 等真实状态 ✅（不再全部显示"-"）

### ECS 执行
```bash
docker exec vigilops-backend-1 \
  python3 /tmp/seed_demo_data.py --clean \
  # DATABASE_URL=postgresql://vigilops:***@postgres:5432/vigilops
```
输出：修复记录 5 条 | 升级规则 1 条 | 升级历史 3 条

---

## 任务二：网络带宽负值 Bug ✅

### 问题
服务器详情页网络带宽图出现负值，是计数器重置时差值计算错误（计数器溢出/重启）。

### 根因
Agent 在系统重启后，`bytes_sent/bytes_recv` 计数器从 0 重新开始，但 `_prev_net` 仍是旧值，导致差值为负。

### 三层防护修复

**层 1 - Agent（`agent/vigilops_agent/collector.py`）**
```python
# Before: 可能产生负值
net_send_rate_kb = round((net.bytes_sent - _prev_net["bytes_sent"]) / 1024 / dt, 2)

# After: max(0) 防止负值
net_send_rate_kb = round(max(0.0, (net.bytes_sent - _prev_net["bytes_sent"]) / 1024 / dt), 2)
```

**层 2 - 后端 SQL（`backend/app/routers/hosts.py`）**
```sql
-- Before
avg(net_send_rate_kb) as net_send_rate_kb,

-- After: GREATEST 处理历史负值
greatest(0, avg(net_send_rate_kb)) as net_send_rate_kb,
```

**层 3 - 前端（`frontend/src/pages/HostDetail.tsx`）**
```typescript
// Before
data: metrics.map(m => m.net_send_rate_kb ?? 0)

// After: Math.max 兜底
data: metrics.map(m => Math.max(0, m.net_send_rate_kb ?? 0))
```

**DB 历史数据清理（ECS 直接执行）**
```sql
UPDATE host_metrics SET net_send_rate_kb = 0 WHERE net_send_rate_kb < 0;  -- 54 rows
UPDATE host_metrics SET net_recv_rate_kb = 0 WHERE net_recv_rate_kb < 0;  -- 53 rows
```

### 验证截图
- 网络带宽图 Y 轴从 0 KB/s 开始，无负值 ✅
- API 验证：`Negative values remaining: 0` ✅

---

## Commit 历史

| Commit | 说明 |
|--------|------|
| `3b4eaa3` | fix: P0 修复 - Demo示例数据+网络带宽负值bug（主要修复） |
| `3054611` | fix: 后端 SQL 用 GREATEST(0, ...) 确保带宽速率不返回负值 |
| `0487efa` | fix: raw 模式也修复带宽负值 - clamp to 0 in Python layer |

---

## Demo 验证路径

1. 访问 http://139.196.210.68:3001
2. 登录：demo@vigilops.io / demo123
3. **自动修复** → 5 条执行记录（4 完成 + 1 失败，有 Runbook 名称、风险级别）
4. **告警中心** → "修复状态"列显示"已完成"/"失败"（不再是"-"）
5. **告警升级** → 历史 Tab 显示 3 条升级记录
6. **服务器详情** → 网络带宽图无负值，Y 轴从 0 开始

