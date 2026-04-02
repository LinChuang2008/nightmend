#!/usr/bin/env bash
# scripts/deploy-ecs.sh — 部署到 ECS（阿里云 demo.lchuangnet.com）
# 用法: bash scripts/deploy-ecs.sh
set -euo pipefail

ECS_HOST="${ECS_HOST:-root@demo.lchuangnet.com}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/nightmend}"
HEALTH_URL="https://demo.lchuangnet.com/health"
HEALTH_TIMEOUT=120   # 等待健康检查最长秒数

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${YELLOW}[INFO]${NC} $*"; }
log_ok()   { echo -e "${GREEN}[OK]${NC}   $*"; }
log_err()  { echo -e "${RED}[ERROR]${NC} $*"; }

# ──────────────────────────────────────────
# 1. SSH 连通性检查
# ──────────────────────────────────────────
log_info "检查 SSH 连通性 → ${ECS_HOST} ..."
if ! ssh -o ConnectTimeout=10 -o BatchMode=yes "${ECS_HOST}" true 2>/dev/null; then
  log_err "SSH 连接失败：${ECS_HOST}"
  echo "  → 请确认 SSH 密钥已配置，并且服务器可达"
  exit 1
fi
log_ok "SSH 连接正常"

# ──────────────────────────────────────────
# 2. 远程部署
# ──────────────────────────────────────────
log_info "开始远程部署到 ${ECS_HOST}:${DEPLOY_DIR} ..."

ssh "${ECS_HOST}" bash -s << REMOTE
set -euo pipefail

cd "${DEPLOY_DIR}"

echo "[远程] 拉取最新代码..."
git pull origin main

echo "[远程] 重建有变更的镜像..."
docker compose build

echo "[远程] 启动/更新服务..."
docker compose up -d

echo "[远程] 当前容器状态："
docker compose ps
REMOTE

log_ok "远程部署命令执行完毕"

# ──────────────────────────────────────────
# 3. 健康检查（从本地请求 ECS）
# ──────────────────────────────────────────
log_info "等待 ECS 后端就绪 (最长 ${HEALTH_TIMEOUT}s)..."
elapsed=0
until curl -sf "${HEALTH_URL}" > /dev/null 2>&1; do
  if [[ $elapsed -ge $HEALTH_TIMEOUT ]]; then
    log_err "ECS 后端在 ${HEALTH_TIMEOUT}s 内未就绪"
    echo "  → 请检查远程日志："
    echo "     ssh ${ECS_HOST} 'cd ${DEPLOY_DIR} && docker compose logs backend --tail=50'"
    exit 1
  fi
  echo -n "."
  sleep 5
  elapsed=$((elapsed + 5))
done
echo ""
log_ok "ECS 后端健康检查通过：${HEALTH_URL}"

# ──────────────────────────────────────────
# 4. 汇总
# ──────────────────────────────────────────
echo ""
echo -e "${GREEN}✅ 部署成功${NC}"
echo "   前端：https://demo.lchuangnet.com"
echo "   API ：${HEALTH_URL%/health}/api/v1/"
