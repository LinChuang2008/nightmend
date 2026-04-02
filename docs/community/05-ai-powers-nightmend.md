# 🤖 How AI Powers NightMend

**Category: Show & Tell**

---

NightMend isn't just another monitoring dashboard with an "AI" label slapped on. AI is deeply integrated into the core workflow — from detection to diagnosis to remediation.

## 1. AI Root Cause Analysis

When an alert fires, most tools just say "disk is full" or "service is down." NightMend asks **why**.

**How it works:**
1. Alert triggers → AI Engine receives the alert context
2. DeepSeek analyzes correlated logs, metrics, and service dependencies
3. Generates a **root cause hypothesis** with confidence scoring
4. Presents findings in a conversational interface — you can ask follow-up questions

**Example:**
```
Alert: Backend API response time > 5s

AI Analysis:
→ PostgreSQL slow query detected (query on `host_metrics` taking 12s)
→ Missing index on `created_at` column
→ Correlated with spike in log ingestion 30 min ago
→ Recommendation: Add index + consider partitioning by date
```

## 2. Auto-Remediation System

This is the game-changer. NightMend doesn't just tell you what's wrong — it **fixes it**.

**The closed-loop pipeline:**
```
Alert → AI Diagnosis → Runbook Selection → Safety Check → Execution → Verification
```

**Safety first:**
- Every remediation goes through a safety check layer
- Critical operations require approval workflow
- All actions are logged in the audit trail
- Rollback capability for each runbook

**6 Built-in Runbooks:**
| Runbook | Trigger Example | What It Does |
|---------|----------------|--------------|
| disk_cleanup | Disk > 90% | Clears temp files, old logs, caches |
| service_restart | Health check fails 3x | Graceful restart with pre/post checks |
| memory_pressure | Memory > 95% | Identifies top consumers, clears caches |
| log_rotation | Log file > 1GB | Rotates, compresses, archives |
| zombie_killer | Zombie count > 10 | Safely terminates zombie processes |
| connection_reset | Connection pool exhausted | Resets stuck connections |

## 3. AI-Powered Topology

The service topology isn't just a static diagram:
- AI **suggests dependencies** based on log and metric correlation
- Automatically detects when services communicate (even if not explicitly configured)
- Health overlay shows real-time status across your entire infrastructure

## 4. Operational Memory (Engram Integration)

NightMend integrates with the **Engram memory system** to build operational context over time:
- Remembers past incidents and their resolutions
- Correlates current issues with historical patterns
- Gets smarter with each incident — learning what works for **your** infrastructure

## 5. Intelligent Alerting

Not all alerts are created equal:
- **Noise reduction** — Cooldown periods prevent alert storms
- **Silence windows** — Schedule maintenance without false alarms
- **Smart correlation** — Groups related alerts into incidents
- **Three rule types** — Metric thresholds, log keywords, database conditions

## What Makes This Different?

Most "AI monitoring" tools bolt on a chatbot to query metrics. NightMend is different:

| Traditional | NightMend |
|------------|----------|
| Alert → human investigates → human fixes | Alert → AI diagnoses → auto-fix |
| Static dashboards | Real-time WebSocket + AI insights |
| Manual dependency mapping | AI-suggested topology |
| Every alert is standalone | Historical pattern matching via memory |

**The result:** Less MTTR, fewer 3 AM pages, and ops teams that focus on architecture instead of firefighting.

---

## 🇨🇳 中文版

### AI 如何驱动 NightMend？

**不是贴标签的 AI，是深度集成的 AI。**

1. **AI 根因分析** — 告警触发后，DeepSeek 自动关联日志、指标、服务依赖，定位根因
2. **自动修复** — 全闭环：告警 → 诊断 → 选择 Runbook → 安全检查 → 执行 → 验证
3. **智能拓扑** — AI 基于日志和指标关联自动推荐服务依赖关系
4. **运维记忆** — Engram 记忆系统记住历史事件，让 AI 越用越聪明
5. **降噪告警** — 冷却期、静默期、智能关联，减少告警风暴

**核心差异：别人的 AI 监控是"AI 帮你查"，我们是"AI 帮你修"。**
