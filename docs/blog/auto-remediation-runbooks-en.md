# Auto-Remediation: What If Your Monitoring System Could Fix Things?

> VigilOps Team | February 2026

---

## The Broken Loop

Here's how incident response works at most organizations:

1. Monitoring detects an anomaly
2. Alert fires
3. Notification sent to on-call
4. Human wakes up / stops what they're doing
5. Human investigates (SSH, dashboards, logs)
6. Human identifies root cause
7. Human executes fix
8. Human verifies the fix worked
9. Human writes a post-mortem saying "we should automate this"
10. Nobody automates it

Steps 5-8 are where time goes. And for a surprisingly large class of incidents — disk full, service crashed, memory leak, log files consuming space — the fix is predictable, repetitive, and scriptable.

Yet ServiceNow's 2025 data shows less than 1% of enterprises have achieved truly autonomous remediation. Why?

## Why Auto-Remediation Is Hard (but Not Impossible)

### The trust problem

The biggest barrier isn't technical — it's psychological. Teams don't trust automated systems to take action in production. And honestly? They're right to be cautious. An auto-remediation system that restarts the wrong service or clears the wrong files is worse than no auto-remediation at all.

This is why most "auto-remediation" features in commercial tools sit unused. They exist in the product, but the security and approval requirements make them impractical, or teams simply don't enable them.

### The integration problem

Even when teams want auto-remediation, the toolchain is fragmented:
- Monitoring in Prometheus/Datadog
- Alerting in PagerDuty
- Runbook documentation in Confluence
- Actual scripts scattered across repos, cron jobs, and engineers' laptops
- Execution via Ansible/Rundeck/SSH

Getting all of these to work together reliably is a project in itself.

### The scope problem

You can't auto-remediate everything. But you can auto-remediate the boring stuff — the incidents that have a known cause and a known fix, that happen repeatedly, and that don't require human judgment.

The key insight: **start with the smallest, safest scope and expand gradually.**

## How VigilOps Does It

VigilOps takes the approach of building remediation directly into the monitoring system, rather than bolting it on as a separate layer.

### The Architecture

```
Alert Rule Triggers
        ↓
AI Analysis (DeepSeek LLM)
  - Reads metrics, logs, topology
  - Determines root cause
  - Assesses severity
        ↓
Runbook Matching
  - Does a built-in runbook apply?
  - Are safety preconditions met?
        ↓
  ┌─── Yes ──────────────────┐
  │                          │
  ▼                          ▼
Auto-Execute              Notify Human
(with audit log)         (with AI analysis attached)
```

### The 6 Built-in Runbooks

Each runbook is designed for a specific, common scenario:

**1. `disk_cleanup`**

Trigger: Disk usage exceeds threshold.
Action: Identifies and removes temp files, old logs, and rotated archives. Targets `/tmp`, `/var/log`, and configurable paths.
Safety: Only deletes files matching known safe patterns. Won't touch application data.

**2. `service_restart`**

Trigger: Service health check fails repeatedly.
Action: Sends graceful shutdown signal, waits for drain, restarts service.
Safety: Checks if the service is configured for restart. Won't restart databases or stateful services without explicit configuration.

**3. `memory_pressure`**

Trigger: Memory usage exceeds threshold.
Action: Identifies top memory consumers, terminates processes that match configurable patterns (e.g., runaway workers, leaked child processes).
Safety: Only kills processes matching allow-list patterns. Core system processes are protected.

**4. `log_rotation`**

Trigger: Specific log files exceed size threshold.
Action: Rotates and compresses the log file, signals the application to reopen file handles.
Safety: Uses standard logrotate patterns. Configurable per application.

**5. `zombie_killer`**

Trigger: Zombie process count exceeds threshold.
Action: Identifies zombie processes and terminates their parent processes.
Safety: Only targets processes in zombie state. Logs all actions.

**6. `connection_reset`**

Trigger: Connection pool exhaustion or stuck connections detected.
Action: Resets connection pools for configured services (database connections, Redis connections, etc.).
Safety: Graceful drain before reset. Configurable timeout.

### Safety Is Not Optional

Every runbook execution goes through:

1. **Precondition checks** — Is this runbook appropriate for this alert? (e.g., don't run disk_cleanup on a disk usage alert caused by database growth)
2. **Dry-run option** — See what would happen without actually doing it
3. **Approval workflows** — Configurable per runbook: auto-approve, require manual approval, or require approval above a severity threshold
4. **Full audit trail** — Every action logged with timestamp, trigger, parameters, and result
5. **Rollback awareness** — Some runbooks can detect if the fix didn't work and flag for human review

## A Real-World Example

Let's walk through a concrete scenario.

**Setup:** You have VigilOps monitoring 10 servers. One of them, `app-02`, runs a Python web application that occasionally leaks memory.

**What happens:**

```
08:23 - Memory usage on app-02 reaches 92%
08:23 - Alert fires: "app-02 memory critical"
08:23 - AI analysis:
        "Memory has been climbing steadily for 6 hours.
         Top consumer: gunicorn worker processes (8 workers, 450MB each).
         This pattern matches a known memory leak in long-running workers.
         Recommended action: restart gunicorn service."
08:23 - Runbook match: service_restart (target: gunicorn on app-02)
08:23 - Safety check: gunicorn is in the restart-allowed service list ✅
08:23 - Execute: Graceful restart with 30s drain timeout
08:24 - Memory drops to 45%
08:24 - Alert auto-resolves
08:24 - Audit log entry created
```

Your on-call engineer sees this in the morning: "app-02 memory alert — auto-resolved via service_restart at 08:24." They might look at the audit log, confirm everything looks normal, and move on. Total human time: 30 seconds.

Without auto-remediation, this would have been a page at 8:23 AM, 15 minutes of investigation, and a manual restart. Not the end of the world, but multiply this by a few times a week across multiple servers, and it adds up.

## Getting Started

### Deploy VigilOps

```bash
git clone https://github.com/LinChuang2008/vigilops.git
cd vigilops
cp .env.example .env    # Add DeepSeek API key
docker compose up -d
```

Open `http://localhost:3001` and explore the Runbook section to see how each built-in runbook works.

### Try the Demo

[https://demo.lchuangnet.com](https://demo.lchuangnet.com) — `demo@vigilops.io` / `demo123` (read-only)

In the demo, navigate to:
- **Runbooks** — See the 6 built-in runbooks with their logic and parameters
- **Audit Log** — See records of past auto-remediation actions
- **Alert Detail** — See how AI analysis connects to runbook recommendations

## Who Should (and Shouldn't) Use This

**Good fit:**
- Small teams (1-5 ops people) managing 10-50 servers
- Teams that repeatedly get paged for the same types of issues
- Organizations that want to experiment with AI-powered operations
- Non-critical environments where you can tolerate some risk in exchange for automation

**Not a good fit (yet):**
- Large-scale production with strict compliance requirements
- Environments needing HA/multi-node monitoring
- Teams that need 100+ integrations (VigilOps ecosystem is still limited)
- Anyone expecting a mature, battle-tested platform (we're early stage — honest)

## The Bigger Picture

Auto-remediation isn't about replacing ops engineers. It's about letting them focus on work that actually requires human judgment — architecture decisions, capacity planning, reliability engineering — instead of restarting services and clearing disk space at 3 AM.

The fact that < 1% of enterprises have achieved autonomous remediation tells us that the tooling gap is real. We don't claim VigilOps closes that gap entirely — we're too early for that. But we think building remediation directly into an open-source monitoring system, with AI to connect alerts to actions, is a step in the right direction.

If this resonates, try it out and let us know what you think: [GitHub Discussions](https://github.com/LinChuang2008/vigilops/discussions).

---

*VigilOps is an Apache 2.0 open source project. [GitHub](https://github.com/LinChuang2008/vigilops)*
