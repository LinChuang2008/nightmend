# Changelog

All notable changes to NightMend will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2026.03.29] - 2026-03-29

### Added
- Prometheus AlertManager Bridge: webhook endpoint at `/api/v1/webhooks/alertmanager` with Bearer token auth, HMAC constant-time verification, and Redis-based deduplication
- Alert source abstraction layer (`AlertSourceAdapter` ABC) with `PrometheusAdapter` implementation for parsing, host mapping, and severity normalization
- Diagnosis-only demo mode (`ENABLE_REMEDIATION=false`): AI root cause analysis via SSE stream at `/api/v1/demo/alerts/stream`, no remediation execution
- Demo page at `/demo`: unauthenticated React page with AlertManager config snippet, real-time alert feed with AI diagnosis, connection status indicator
- AI engine integration for alert diagnosis with memory system recall and fault pattern storage
- AI deep thinking support: `supports_deep_thinking` and `deep_thinking_max_tokens` config, reasoning content display with collapsible UI
- AI config center page (`/ai-configs`) for managing AI model parameters
- Agent self-monitoring: CPU, RSS memory, thread count, uptime, open file descriptors reported to backend
- Host detail page shows agent resource metrics
- Custom runbook management: `match_alert_types`, `safety_checks`, `verify_commands`, and rollback support
- Database monitoring targets management (`/databases`)
- 12 new tests: webhook auth, alert processing, diagnosis flow, SSE endpoint, remediation gating, config defaults

### Security
- OAuth race condition fix in external auth callback
- WebSocket connection leak prevention in dashboard WS
- Template injection prevention in notification templates (Jinja2 sandboxing)
- Webhook SSL verification enforcement
- `shlex.quote` for shell argument injection prevention in command executor
- SSH host key enforcement for remediation connections
- SSE endpoint middleware bypass for streaming (SecurityMiddleware, RequestSizeMiddleware, RateLimitMiddleware)

### Changed
- MCP server refactored for cleaner tool organization
- MCP server bug fixes: DB connection leak (context manager), N+1 queries (batch preload), auth bypass (WebSocket bearer validation)
- Notification and settings API improvements
- Frontend AppLayout responsive sidebar enhancements
- Agent reporter hardened with connection retry and error handling
- Runbook registry refactored: alert type matching with keyword scoring priority
- OPS assistant session stability: fixed cross-session leaks, duplicate sessions, blank session bugs
- OpenAI-compatible streaming: tolerates empty `choices` array in SSE chunks

### Fixed
- All CI test imports repaired: `AIEngine` → `llm_client`, `RemediationAIClient` → `RemediationLLMClient`
- JWT test fixtures now include `session_id` for auth session validation
- Test mocks updated for merged stats query and tightened rm patterns
- Agent WS token validation and OPS command timeout handling
- Docker backend startup path fixed with `PYTHONPATH=/app`

## [2026.03.14] - 2026-03-14

> Version scheme changed to date-based: vYYYY.MM.DD (beta: vYYYY.MM.DD-beta.N)

### Added
- PromQL query support (`/api/v1/promql/query`, `/query_range`, `/metadata`)
- Helm Chart for Kubernetes deployment (`charts/nightmend/`)
- Slack and Telegram notification channels
- Alert service test coverage (26 new tests)

### Security
- SQL injection fix in ClickHouse log backend (P0)
- Command injection prevention in remediation executor (P1)
- MCP server forced Bearer Token authentication (P1)
- OAuth state migrated from memory to Redis (P1)
- Notification channel config sanitization in API responses
- Settings/Remediation endpoints restricted to operator+ role
- CORS headers whitelist tightened
- Removed production server IP from all public documentation

### Fixed
- Service alert rules now respect duration_seconds threshold
- Notification retry with exponential backoff
- Log keyword alert deduplication (60s window)
- Silence window timezone fix (UTC)
- WebSocket send timeout for slow consumers
- Orphaned alert cleanup runs periodically

## [0.9.1] - 2026-03-07

### Added
- **i18n Full Coverage**: Settings page internationalized — 100% of UI now supports EN/ZH switching

### Fixed
- **JWT Security**: Migrated from localStorage to httpOnly Cookie, eliminating XSS token exposure
- **Auto-Remediation**: Alert name and host columns in remediation list now display correctly (was blank)

### Improved
- Demo environment: AI Chat timeout increased to 60s, new users default to operator role

## [0.9.0] - 2026-02-20

### Added
- **Agent Installer**: One-line install script with offline mode support (`scripts/install-agent.sh`)
- **CI/CD Pipeline**: GitHub Actions for automated build, test, and Docker image push
- **Customer Onboarding SOP**: Step-by-step deployment guide for service delivery
- **Blog Content**: 6 technical articles (zh/en) covering AI observability trends, quick start guide, and Agentic SRE
- **Landing Page Copy**: README redesigned as product landing page with feature highlights

### Improved
- README.md restructured for better GitHub discoverability and conversion
- Agent install script supports both online and offline deployment modes

## [0.8.0] - 2026-02-19

### Added
- **Multi-Server Topology**: Hierarchical drill-down topology view (L1 global → L2 server → L3 service)
- Topology supports drag-and-drop layout with persistence
- AI-suggested service dependencies in topology view
- Adjacency highlighting for connected services

### Improved
- Topology rendering performance for large service graphs
- Server group management with topology integration

## [0.7.0] - 2026-02-18

### Added
- **AI Memory Integration**: NightMend AI engine connected to Engram for fault history recall
- AI analysis recalls past incidents for better root cause diagnosis
- Resolved incidents auto-stored as operational knowledge
- GitHub open-source materials: CONTRIBUTING.md, issue templates, PR template

### Changed
- AI engine uses historical context for smarter anomaly detection

## [0.6.0] - 2026-02-18

### Added
- **ECS Deployment**: Full stack deployed to Alibaba Cloud ECS (demo.lchuangnet.com)
- Docker Compose production configuration
- Migration 014 for production database

### Fixed
- Docker build optimizations for smaller image size
- Environment variable handling for production deployment

## [0.5.0] - 2026-02-17

### Added
- **SLA Management**: Availability tracking, error budgets, violation detection
- **Audit Logging**: Full operation audit trail
- **Notification System**: 5 channels (DingTalk, Feishu, WeCom, Email, Webhook)
- Notification templates with variable substitution
- Notification throttling (cooldown + silence periods)

## [0.4.0] - 2026-02-17

### Added
- **Auto-Remediation System**: AI-driven self-healing for common incidents
- 6 built-in runbooks: disk cleanup, memory pressure, service restart, log rotation, zombie killer, connection reset
- Safety checks with approval workflow for destructive operations
- Remote command execution via SSH

## [0.3.0] - 2026-02-16

### Added
- **Dashboard**: Real-time WebSocket updates, health score, trend charts
- **Database Monitoring**: PostgreSQL, MySQL, Oracle support with slow query Top10
- **Log Management**: Collection, full-text search, real-time streaming
- **Report Generation**: Automated operational reports

## [0.2.0] - 2026-02-16

### Added
- **AI Analysis Module**: DeepSeek integration for intelligent diagnostics
- AI conversation interface for interactive troubleshooting
- Root cause analysis with one-click trigger from alerts
- AI insights dashboard with severity scoring

## [0.1.0] - 2026-02-16

### Added
- **Core Monitoring**: Host and service monitoring with metric collection
- **Alert System**: Metric-based, log keyword, and database alert rules
- **User Management**: Registration, login, JWT auth, RBAC
- **Agent**: Data collection agent with HTTP reporting
- FastAPI backend + React frontend + PostgreSQL + Redis
