#!/bin/bash
# NightMend GitHub Growth Setup Script
# Run this script when GitHub API is reachable.
# Prerequisites: gh CLI authenticated (gh auth login)

set -euo pipefail

REPO="LinChuang2008/nightmend"

echo "=== NightMend GitHub Growth Setup ==="
echo ""

# ---- 1. Set GitHub Topics ----
echo "[1/5] Setting GitHub Topics..."
gh repo edit "$REPO" \
  --add-topic monitoring \
  --add-topic ai \
  --add-topic devops \
  --add-topic mcp \
  --add-topic auto-remediation \
  --add-topic aiops \
  --add-topic alerting \
  --add-topic observability \
  --add-topic self-healing \
  --add-topic fastapi \
  --add-topic react \
  --add-topic open-source \
  --add-topic infrastructure-monitoring \
  --add-topic incident-response
echo "  Topics set."

# ---- 2. Create GitHub Releases ----
echo "[2/5] Creating GitHub Releases..."

# v0.9.0 Release
if ! gh release view v0.9.0 -R "$REPO" &>/dev/null; then
  gh release create v0.9.0 \
    -R "$REPO" \
    --title "v0.9.0 — Agent Installer & CI/CD Pipeline" \
    --notes "$(cat <<'NOTES'
## What's New in v0.9.0

### Added
- **Agent Installer**: One-line install script with offline mode support (`scripts/install-agent.sh`)
- **CI/CD Pipeline**: GitHub Actions for automated build, test, and Docker image push
- **Blog Content**: 6 technical articles (zh/en) covering AI observability, quick start, and Agentic SRE

### Improved
- README.md restructured as product landing page
- Agent install supports both online and offline deployment

### Quick Start
```bash
git clone https://github.com/LinChuang2008/nightmend.git && cd nightmend
cp .env.example .env   # Add your DeepSeek API key
docker compose up -d
# Open http://localhost:3001
```

**Full Changelog**: https://github.com/LinChuang2008/nightmend/blob/main/CHANGELOG.md
NOTES
)" \
    --latest=false
  echo "  v0.9.0 release created."
else
  echo "  v0.9.0 release already exists, skipping."
fi

# v0.9.1 Release
if ! gh release view v0.9.1 -R "$REPO" &>/dev/null; then
  gh release create v0.9.1 \
    -R "$REPO" \
    --title "v0.9.1 — Security Hardening & Full i18n" \
    --notes "$(cat <<'NOTES'
## What's New in v0.9.1

### Added
- **i18n Full Coverage**: Settings page internationalized — 100% of UI now supports EN/ZH switching

### Security
- **JWT Security**: Migrated from localStorage to httpOnly Cookie, eliminating XSS token exposure

### Fixed
- Auto-Remediation: Alert name and host columns now display correctly (was blank)

### Improved
- Demo environment: AI Chat timeout increased to 60s, new users default to operator role

### Quick Start
```bash
git clone https://github.com/LinChuang2008/nightmend.git && cd nightmend
cp .env.example .env   # Add your DeepSeek API key
docker compose up -d
```

**Full Changelog**: https://github.com/LinChuang2008/nightmend/blob/main/CHANGELOG.md
NOTES
)" \
    --latest=true
  echo "  v0.9.1 release created."
else
  echo "  v0.9.1 release already exists, skipping."
fi

# ---- 3. Create Good First Issues ----
echo "[3/5] Creating Good First Issues..."

# Ensure label exists
gh label create "good first issue" --color 7057ff --description "Good for newcomers" -R "$REPO" 2>/dev/null || true
gh label create "help wanted" --color 008672 --description "Extra attention is needed" -R "$REPO" 2>/dev/null || true
gh label create "documentation" --color 0075ca --description "Improvements or additions to documentation" -R "$REPO" 2>/dev/null || true
gh label create "enhancement" --color a2eeef --description "New feature or request" -R "$REPO" 2>/dev/null || true

# Issue 1: Add PromQL support
gh issue create -R "$REPO" \
  --title "Add PromQL query support for custom metrics" \
  --label "good first issue,enhancement" \
  --body "$(cat <<'BODY'
## Description
NightMend currently uses built-in metric queries. Adding PromQL-style query support would allow users to write custom metric expressions.

## Suggested Approach
- Add a PromQL parser in `backend/app/services/`
- Support basic operations: rate(), avg(), sum(), histogram_quantile()
- Connect to the existing metrics storage

## Why This Matters
PromQL is the industry standard for metric queries. Supporting it lowers the barrier for teams migrating from Prometheus.

## Getting Started
1. Read `backend/app/services/metrics_service.py`
2. Check `backend/app/models/alert_rule.py` for current query format
3. Run tests: `cd backend && python -m pytest tests/ -x`
BODY
)"

# Issue 2: Add Helm Chart
gh issue create -R "$REPO" \
  --title "Create Helm Chart for Kubernetes deployment" \
  --label "good first issue,help wanted" \
  --body "$(cat <<'BODY'
## Description
NightMend currently supports Docker Compose deployment. A Helm Chart would make it easy to deploy on Kubernetes clusters.

## Suggested Approach
- Create `charts/nightmend/` directory with standard Helm chart structure
- Include templates for: backend Deployment, frontend Deployment, PostgreSQL StatefulSet, Redis Deployment
- Support configurable values for resource limits, replicas, and environment variables
- Reference: `docker-compose.yml` for service definitions

## Getting Started
1. Review `docker-compose.yml` and `docker-compose.dev.yml`
2. Check environment variables in `.env.example`
3. Test with: `helm template nightmend charts/nightmend/`
BODY
)"

# Issue 3: Add more notification channels
gh issue create -R "$REPO" \
  --title "Add Slack and Telegram notification channels" \
  --label "good first issue,enhancement" \
  --body "$(cat <<'BODY'
## Description
NightMend supports DingTalk, Feishu, WeCom, Email, and Webhook notifications. Adding Slack and Telegram would serve international users.

## Suggested Approach
- Add new channel types in `backend/app/services/notification_service.py`
- Follow the existing pattern for DingTalk/Feishu channels
- Add corresponding frontend forms in notification settings

## Getting Started
1. Read `backend/app/services/notification_service.py` for existing channel implementations
2. Check `backend/app/models/notification.py` for the data model
3. Frontend notification form: `frontend/src/pages/Settings/`
BODY
)"

# Issue 4: Improve test coverage
gh issue create -R "$REPO" \
  --title "Improve backend test coverage for alert service" \
  --label "good first issue,help wanted" \
  --body "$(cat <<'BODY'
## Description
The alert service is a core component but needs better test coverage. This is a great way to learn the codebase.

## Suggested Approach
- Add unit tests for `backend/app/services/alert_service.py`
- Cover: alert creation, threshold evaluation, deduplication logic, cooldown handling
- Use pytest-asyncio for async test support

## Getting Started
1. Read `backend/app/services/alert_service.py`
2. Check existing tests in `backend/tests/`
3. Run: `cd backend && python -m pytest tests/ -x --tb=short`
BODY
)"

# Issue 5: Add dark mode improvements
gh issue create -R "$REPO" \
  --title "Fix dark mode inconsistencies across dashboard pages" \
  --label "good first issue,enhancement" \
  --body "$(cat <<'BODY'
## Description
Some dashboard pages have inconsistent dark mode styling — hardcoded colors instead of using theme tokens.

## Suggested Approach
- Audit ECharts chart components for hardcoded colors
- Replace with Ant Design theme tokens (useToken hook)
- Test both light and dark modes

## Getting Started
1. Check `frontend/src/pages/Dashboard/` components
2. Look for hardcoded color values like `#fff`, `#333`, `rgba(...)`
3. Run: `cd frontend && npm run dev` to test changes
BODY
)"

echo "  5 good first issues created."

# ---- 4. Enable Discussions ----
echo "[4/5] Enabling GitHub Discussions..."
# Note: Discussions must be enabled via GitHub web UI (Settings > Features > Discussions)
# The gh CLI cannot enable this directly. Print instructions instead.
echo "  ACTION REQUIRED: Enable Discussions manually:"
echo "    1. Go to https://github.com/$REPO/settings"
echo "    2. Scroll to 'Features' section"
echo "    3. Check 'Discussions'"
echo "    4. Then run: scripts/github-post-discussions.sh"

# ---- 5. Update repo description ----
echo "[5/5] Updating repo description..."
gh repo edit "$REPO" \
  --description "AI-powered open-source monitoring platform with auto-remediation. 6 built-in runbooks, MCP integration (global first), DeepSeek root cause analysis. 5-minute Docker setup." \
  --homepage "https://demo.lchuangnet.com"
echo "  Description updated."

echo ""
echo "=== Setup Complete ==="
echo "Next steps:"
echo "  1. Enable Discussions in GitHub Settings"
echo "  2. Run scripts/github-post-discussions.sh after enabling Discussions"
echo "  3. Run scripts/submit-awesome-lists.sh to prepare awesome-list PRs"
