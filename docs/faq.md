# 常见问题 (FAQ)

> NightMend 使用过程中的常见问题与解答。

## 目录

- [1. Agent 连不上服务端怎么办？](#1-agent-连不上服务端怎么办)
- [2. 告警太多怎么调？](#2-告警太多怎么调)
- [3. 告警太少/收不到？](#3-告警太少收不到)
- [4. AI 分析不准怎么办？](#4-ai-分析不准怎么办)
- [5. 如何备份数据？](#5-如何备份数据)
- [6. 如何升级 NightMend？](#6-如何升级-nightmend)
- [7. 端口被占用怎么办？](#7-端口被占用怎么办)
- [8. 自动修复安全吗？](#8-自动修复安全吗)
- [9. 支持哪些数据库监控？](#9-支持哪些数据库监控)
- [10. 如何添加自定义 Runbook？](#10-如何添加自定义-runbook)

---

## 1. Agent 连不上服务端怎么办？

**排查步骤：**

1. **检查服务端 URL**：确认 `agent.yaml` 中的 `server_url` 配置正确，默认端口为 `8001`。

   ```yaml
   # agent.yaml
   server_url: http://<服务端IP>:8001
   ```

2. **检查 Agent Token**：确认 token 与服务端「Agent Token 管理」页面中生成的一致且未过期。

   ```yaml
   token: <your-agent-token>
   ```

3. **检查防火墙/安全组**：确保服务端的 `8001` 端口对 Agent 所在网络开放。

   ```bash
   # 在 Agent 机器上测试连通性
   curl -v http://<服务端IP>:8001/api/health
   ```

4. **检查服务端是否运行**：

   ```bash
   docker compose ps   # 确认 backend 容器状态为 running
   docker compose logs backend --tail=50  # 查看后端日志
   ```

5. **检查网络策略**：如果 Agent 和服务端在不同 VPC/网段，确认路由和 NAT 配置。

---

## 2. 告警太多怎么调？

**方法一：调整告警规则阈值**

在「告警规则」页面找到触发频繁的规则，提高阈值。例如将 CPU 告警阈值从 70% 调到 85%。

**方法二：启用通知降噪**

NightMend 内置两种降噪机制：

- **冷却期 (Cooldown)**：同一告警在冷却期内不重复通知。在通知渠道配置中设置 `cooldown` 时间（单位：秒）。
- **静默期 (Silence)**：临时屏蔽特定告警的通知，用于维护窗口等场景。在告警列表中对特定告警设置静默。

**方法三：调整告警级别**

将低优先级的规则降级为 `warning`，仅对 `critical` 级别发送即时通知。

---

## 3. 告警太少/收不到？

**排查步骤：**

1. **确认告警规则已启用**：进入「告警规则」页面，检查规则状态是否为"启用"。
2. **检查规则匹配条件**：阈值是否设置得过高，导致永远不会触发？
3. **确认通知渠道已配置**：进入「通知渠道」页面，确认至少有一个渠道（钉钉/飞书/企微/邮件/Webhook）配置正确。
4. **发送测试通知**：在通知渠道配置页面点击「测试」按钮，验证通知能否正常到达。
5. **查看通知日志**：进入「通知日志」页面，查看是否有发送失败的记录及错误信息。
6. **确认 Agent 在上报数据**：在主机详情页检查指标数据是否在持续更新。

---

## 4. AI 分析不准怎么办？

NightMend 的 AI 分析基于 DeepSeek API，需要以下条件：

1. **检查 AI API Key 配置**：

   ```bash
   # 在 .env 中确认配置
   AI_API_KEY=sk-xxxxxxxxxxxx
   AI_API_BASE_URL=https://api.deepseek.com   # 默认值
   ```

2. **确保有足够的数据**：AI 分析需要足够的日志和指标数据才能给出准确判断。刚部署的系统数据量少，分析结果可能不够精准。建议运行至少 24 小时后再评估。

3. **提供上下文**：在 AI 对话界面中，描述问题时尽量具体，包含时间范围、受影响的服务名称等信息。

4. **检查 API 可用性**：

   ```bash
   # 测试 DeepSeek API 连通性
   curl -s https://api.deepseek.com/v1/models \
     -H "Authorization: Bearer $AI_API_KEY" | head -c 200
   ```

---

## 5. 如何备份数据？

### 备份 PostgreSQL 数据库

```bash
# 使用 Docker 中的 PostgreSQL
docker compose exec postgres pg_dump -U nightmend nightmend > backup_$(date +%Y%m%d).sql

# 恢复
docker compose exec -T postgres psql -U nightmend nightmend < backup_20260221.sql
```

### 备份配置文件

```bash
# 备份关键配置
cp .env .env.backup
cp agent.yaml agent.yaml.backup

# 建议也备份 docker-compose.yml（如有自定义修改）
cp docker-compose.yml docker-compose.yml.backup
```

### 建议

- 设置定时备份（crontab），至少每日一次
- 将备份文件存储到异地（如对象存储）

---

## 6. 如何升级 NightMend？

```bash
# 1. 备份数据（参考上一问）
docker compose exec postgres pg_dump -U nightmend nightmend > backup_before_upgrade.sql

# 2. 拉取最新代码
git pull origin main

# 3. 重新构建并启动
docker compose up -d --build

# 4. 检查服务状态
docker compose ps
docker compose logs --tail=20
```

> ⚠️ 升级前请查看 CHANGELOG 或 Release Notes，了解是否有 breaking changes 或数据库迁移。

---

## 7. 端口被占用怎么办？

修改 `docker-compose.yml` 中的端口映射：

```yaml
services:
  backend:
    ports:
      - "8002:8001"    # 将宿主机端口从 8001 改为 8002
  frontend:
    ports:
      - "3002:80"      # 将宿主机端口从 3001 改为 3002
  postgres:
    ports:
      - "5434:5432"    # 修改 PostgreSQL 映射端口
  redis:
    ports:
      - "6381:6379"    # 修改 Redis 映射端口
```

修改后重启：

```bash
docker compose up -d
```

> 注意：如果修改了 backend 端口，需要同步更新 Agent 的 `server_url` 配置和前端的 API 地址。

---

## 8. 自动修复安全吗？

NightMend 的自动修复系统有多重安全保障：

| 安全机制 | 说明 |
|---------|------|
| **Dry Run 模式** | 默认 `dry_run=true`，仅模拟执行不实际操作。确认无误后再关闭 |
| **安全检查** | 执行前自动检查命令合法性，拒绝危险操作 |
| **审批流** | 高风险操作需要管理员审批后才执行 |
| **速率限制** | 限制单位时间内的修复执行次数，防止风暴 |
| **熔断器** | 连续失败达到阈值后自动停止，避免反复执行失败操作 |

**内置 6 个 Runbook**：磁盘清理、内存释放、服务重启、日志轮转、僵尸进程清理、连接重置。每个都经过安全设计。

**建议**：生产环境首次使用时保持 `dry_run=true`，在「自动修复」页面观察模拟结果，确认符合预期后再开启实际执行。

---

## 9. 支持哪些数据库监控？

目前支持三种数据库：

| 数据库 | 监控指标 |
|--------|---------|
| **PostgreSQL** | 连接数、QPS、慢查询 Top10、缓存命中率、表膨胀等 |
| **MySQL** | 连接数、QPS、慢查询、InnoDB 缓冲池等 |
| **Oracle** | 会话数、表空间使用率、慢查询等 |

在「数据库监控」页面添加数据库连接信息即可开始监控。

---

## 10. 如何添加自定义 Runbook？

1. **创建 Runbook 文件**，继承 `RunbookDefinition`：

   ```python
   # backend/app/remediation/runbooks/my_custom_runbook.py
   from app.remediation.runbook_registry import RunbookDefinition, RunbookRegistry

   class MyCustomRunbook(RunbookDefinition):
       name = "my_custom_action"
       description = "自定义修复操作"
       risk_level = "medium"  # low / medium / high

       async def check(self, context: dict) -> bool:
           """判断是否需要执行"""
           return True

       async def execute(self, context: dict) -> dict:
           """执行修复逻辑"""
           # 你的修复逻辑
           return {"status": "success", "message": "执行完成"}

       async def rollback(self, context: dict) -> dict:
           """回滚操作（可选）"""
           return {"status": "rolled_back"}
   ```

2. **注册到 RunbookRegistry**：

   ```python
   # 在 runbook 模块的 __init__.py 或启动时注册
   RunbookRegistry.register(MyCustomRunbook())
   ```

3. **重启后端服务**使其生效：

   ```bash
   docker compose restart backend
   ```

> 更多开发细节请参考 [贡献指南](./contributing.md)。
