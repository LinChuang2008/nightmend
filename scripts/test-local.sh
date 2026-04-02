#!/usr/bin/env bash
# scripts/test-local.sh — 本地 Docker 环境冒烟测试
# 用法: bash scripts/test-local.sh
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
TEST_EMAIL="${TEST_EMAIL:-demo@nightmend.io}"
TEST_PASSWORD="${TEST_PASSWORD:-demo123}"
TIMEOUT=120   # 等待健康检查最长秒数

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

FAILED_CASES=()

log_info()  { echo -e "${YELLOW}[INFO]${NC} $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}   $*"; }
log_fail()  { echo -e "${RED}[FAIL]${NC} $*"; FAILED_CASES+=("$*"); }

# ──────────────────────────────────────────
# 1. 确保 Docker 服务已启动
# ──────────────────────────────────────────
log_info "检查 Docker Compose 服务状态..."

RUNNING=$(docker compose ps --services --filter "status=running" 2>/dev/null | wc -l | tr -d ' ')
if [[ "$RUNNING" -lt 2 ]]; then
  log_info "服务未完全启动，执行 docker compose up -d ..."
  docker compose up -d
fi

# ──────────────────────────────────────────
# 2. 等待后端健康检查通过
# ──────────────────────────────────────────
log_info "等待后端就绪 (最长 ${TIMEOUT}s)..."
elapsed=0
until curl -sf "${BASE_URL}/health" > /dev/null 2>&1; do
  if [[ $elapsed -ge $TIMEOUT ]]; then
    echo -e "${RED}[ERROR]${NC} 后端在 ${TIMEOUT}s 内未就绪，放弃等待"
    echo "  → 请检查: docker compose logs backend --tail=50"
    exit 1
  fi
  echo -n "."
  sleep 5
  elapsed=$((elapsed + 5))
done
echo ""
log_ok "后端已就绪"

# ──────────────────────────────────────────
# 3. 冒烟测试函数
# ──────────────────────────────────────────
check() {
  local desc="$1"
  local method="$2"
  local url="$3"
  shift 3
  local extra_args=("$@")

  local status
  status=$(curl -s -o /dev/null -w "%{http_code}" -X "$method" \
    -H "Content-Type: application/json" \
    "${extra_args[@]}" \
    "${BASE_URL}${url}" 2>/dev/null)

  if [[ "$status" =~ ^2 ]]; then
    log_ok "${desc} → HTTP ${status}"
  else
    log_fail "${desc} → HTTP ${status} (${method} ${url})"
  fi
}

# ──────────────────────────────────────────
# 4. Case 1: 健康检查
# ──────────────────────────────────────────
log_info "--- 冒烟测试开始 ---"
check "GET /health" GET "/health"

# ──────────────────────────────────────────
# 5. Case 2: 登录获取 Cookie
# ──────────────────────────────────────────
log_info "登录测试账号 ${TEST_EMAIL} ..."
COOKIE_JAR=$(mktemp)
LOGIN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${TEST_EMAIL}\",\"password\":\"${TEST_PASSWORD}\"}" \
  -c "${COOKIE_JAR}" 2>/dev/null)

if [[ "$LOGIN_STATUS" =~ ^2 ]]; then
  log_ok "POST /api/v1/auth/login → HTTP ${LOGIN_STATUS}"
else
  log_fail "POST /api/v1/auth/login → HTTP ${LOGIN_STATUS}"
  log_info "无法登录，跳过需要认证的接口测试"
  rm -f "${COOKIE_JAR}"
  # 汇总
  if [[ ${#FAILED_CASES[@]} -gt 0 ]]; then
    echo ""
    echo -e "${RED}❌ 测试失败 (${#FAILED_CASES[@]} 个接口)：${NC}"
    for f in "${FAILED_CASES[@]}"; do echo "  - $f"; done
    exit 1
  fi
  exit 0
fi

# ──────────────────────────────────────────
# 6. 认证接口冒烟测试（使用 Cookie）
# ──────────────────────────────────────────
AUTH_ARGS=(-b "${COOKIE_JAR}")

check "GET /api/v1/hosts"              GET "/api/v1/hosts"              "${AUTH_ARGS[@]}"
check "GET /api/v1/alerts"             GET "/api/v1/alerts"             "${AUTH_ARGS[@]}"
check "GET /api/v1/dashboard/summary"  GET "/api/v1/dashboard/summary"  "${AUTH_ARGS[@]}"
check "GET /api/v1/topology"           GET "/api/v1/topology"           "${AUTH_ARGS[@]}"
check "GET /api/v1/users/me"           GET "/api/v1/users/me"           "${AUTH_ARGS[@]}"

rm -f "${COOKIE_JAR}"

# ──────────────────────────────────────────
# 7. 汇总
# ──────────────────────────────────────────
echo ""
if [[ ${#FAILED_CASES[@]} -eq 0 ]]; then
  echo -e "${GREEN}✅ 本地测试全部通过，可以推送${NC}"
  exit 0
else
  echo -e "${RED}❌ 以下接口测试失败 (${#FAILED_CASES[@]} 个)：${NC}"
  for f in "${FAILED_CASES[@]}"; do echo "  - $f"; done
  echo ""
  echo "排查建议："
  echo "  docker compose logs backend --tail=100"
  exit 1
fi
