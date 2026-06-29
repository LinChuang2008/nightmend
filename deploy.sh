#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# NightMend 一键部署脚本
#
# 用法（在仓库根目录执行）:
#     bash deploy.sh                  # 默认端口 3001 · 随机密码 · 含 demo 数据
#     bash deploy.sh --port 8080      # 改前端端口
#     bash deploy.sh --no-seed        # 不塞 demo 数据
#     bash deploy.sh --env-file PATH  # 用自定义 .env
#     bash deploy.sh --upgrade        # 升级已部署实例（git pull + 重启）
#     bash deploy.sh --help
#
# 与其他脚本的区别:
#     install.sh          交互式 · 引导新手填配置
#     quickstart.sh       5 分钟体验 · 内置 demo 数据 + 样本主机
#     deploy.sh (本脚本)  零交互一键 · 生产幂等 · 打印访问 URL/凭据
#     scripts/deploy.sh   内部 CI · 接 tarball 重建（非终端用户用）
#
# 幂等：已有 .env 的机器重复执行不会覆盖密钥，只做 pull + up + migration。
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── 颜色 ────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "\n${CYAN}▶ $*${NC}"; }
die()   { err "$*"; exit 1; }

# ── 参数 ────────────────────────────────────────────────
FRONTEND_PORT=3001
BACKEND_PORT=8000
SEED_DEMO=true
ENV_FILE=""
SKIP_PULL=false
AUTO_UPDATE=false

usage() {
  cat <<'EOF'
NightMend 一键部署脚本

用法:
    bash deploy.sh [选项]

选项:
    --port N              前端端口（默认 3001）
    --backend-port N      后端端口（默认 8000）
    --no-seed             跳过 demo 数据
    --env-file PATH       使用指定 .env 文件
    --skip-pull           跳过 docker compose pull（离线场景）
    --upgrade             升级已部署实例
    --help, -h            打印本帮助

示例:
    bash deploy.sh                        # 首次部署
    bash deploy.sh --port 8080            # 改前端端口
    bash deploy.sh --upgrade              # 升级
    bash deploy.sh --env-file ./prod.env  # 用指定配置
EOF
  exit 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --port=*)         FRONTEND_PORT="${1#*=}"; shift ;;
    --port)           shift; FRONTEND_PORT="$1"; shift ;;
    --backend-port=*) BACKEND_PORT="${1#*=}"; shift ;;
    --backend-port)   shift; BACKEND_PORT="$1"; shift ;;
    --no-seed)        SEED_DEMO=false; shift ;;
    --env-file=*)     ENV_FILE="${1#*=}"; shift ;;
    --env-file)       shift; ENV_FILE="$1"; shift ;;
    --skip-pull)      SKIP_PULL=true; shift ;;
    --upgrade)        AUTO_UPDATE=true; shift ;;
    --help|-h)        usage ;;
    *)                warn "忽略未知参数: $1"; shift ;;
  esac
done

# ── 0. 切仓库根目录 ─────────────────────────────────────
cd "$(dirname "$0")"
[ -f docker-compose.yml ] || die "未找到 docker-compose.yml · 请在仓库根目录执行 deploy.sh"

# ── 随机字符串 ──────────────────────────────────────────
rand() {
  local n="${1:-32}"
  if command -v openssl >/dev/null; then
    openssl rand -base64 $((n * 3 / 4 + 1)) | tr -dc 'A-Za-z0-9' | head -c "$n"
  else
    LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$n"
  fi
  echo
}

# ── 跨平台 sed -i ───────────────────────────────────────
_sed_inplace() {
  # _sed_inplace 'expr' file
  if sed --version >/dev/null 2>&1; then
    sed -i "$1" "$2"
  else
    sed -i '' "$1" "$2"
  fi
}

# ── 环境体检 ────────────────────────────────────────────
step "0/6 · 环境体检"
command -v docker >/dev/null || die "未装 Docker · 先装 Docker 24+ 再跑本脚本"
docker info >/dev/null 2>&1 || die "Docker daemon 未运行或无权限（试试 sudo 或加用户进 docker 组）"

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  die "未装 docker compose"
fi
ok "Docker / Compose 就绪 · 引擎 $(docker version -f '{{.Server.Version}}' 2>/dev/null || echo unknown)"

check_port_free() {
  local p="$1" name="$2"
  if lsof -nP -iTCP:"$p" -sTCP:LISTEN 2>/dev/null | grep -q LISTEN; then
    warn "端口 $p ($name) 已被占用 · 若非本脚本启动的容器请先释放"
  fi
}
check_port_free "$FRONTEND_PORT" "frontend"
check_port_free "$BACKEND_PORT"  "backend"

# ── 健康轮询 ────────────────────────────────────────────
_wait_healthy() {
  local max=60 i=0
  while [ $i -lt $max ]; do
    if curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${BACKEND_PORT}/api/v1/health" 2>/dev/null | grep -q 200; then
      ok "后端健康"; return 0
    fi
    sleep 2; i=$((i + 1))
    [ $((i % 5)) -eq 0 ] && info "  等待后端就绪… ${i}/${max}"
  done
  warn "后端 120s 未健康 · 请手动查 ${COMPOSE} logs backend"
  return 1
}

# ── 打印访问信息 ────────────────────────────────────────
_print_access() {
  local ip
  ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<host>")
  [ -z "$ip" ] && ip="<host>"

  echo ""
  echo "══════════════════════════════════════════════════════════"
  echo -e "${GREEN}  🎉  NightMend 部署完成${NC}"
  echo "══════════════════════════════════════════════════════════"
  echo ""
  echo "  🌐 前端地址:"
  echo "       http://${ip}:${FRONTEND_PORT}"
  echo "       http://127.0.0.1:${FRONTEND_PORT}  (本机)"
  echo ""
  if [ -f .deploy-credentials.txt ]; then
    echo "  🔑 初始凭据（已保存到 ${PWD}/.deploy-credentials.txt）:"
    grep "^Admin " .deploy-credentials.txt | sed 's/^/       /'
  fi
  echo ""
  echo "  📋 常用命令:"
  echo "       $COMPOSE ps                  # 查状态"
  echo "       $COMPOSE logs -f backend     # 后端日志"
  echo "       $COMPOSE restart backend     # 重启后端"
  echo "       bash deploy.sh --upgrade     # 一键升级"
  echo ""
  echo "══════════════════════════════════════════════════════════"
}

# ── 升级模式 ────────────────────────────────────────────
if [ "$AUTO_UPDATE" = true ]; then
  step "1/5 · 升级 · git pull"
  if git -C . rev-parse --git-dir >/dev/null 2>&1; then
    git -C . pull --ff-only || warn "git pull 未 fast-forward · 继续用当前 HEAD"
  else
    warn "目录不在 git 仓库里 · 跳过 pull（如从 tarball 装，请先手动替换源码）"
  fi
  step "2/5 · 拉新镜像"
  [ "$SKIP_PULL" = false ] && $COMPOSE pull || true
  step "3/5 · 滚动重启"
  $COMPOSE up -d
  step "4/5 · migration"
  $COMPOSE exec -T backend alembic upgrade head || warn "alembic 失败（忽略可继续）"
  step "5/5 · 健康检查"
  _wait_healthy || true
  _print_access
  exit 0
fi

# ── 生成 .env（幂等） ──────────────────────────────────
step "1/6 · 准备 .env"
if [ -n "$ENV_FILE" ]; then
  [ -f "$ENV_FILE" ] || die "--env-file 指定文件不存在: $ENV_FILE"
  cp "$ENV_FILE" .env
  ok "使用指定 .env: $ENV_FILE"
elif [ -f .env ]; then
  ok ".env 已存在 · 保留现有配置（幂等）"
else
  [ -f .env.example ] || die "未找到 .env.example · 无法自动生成"
  cp .env.example .env

  POSTGRES_PASSWORD=$(rand 32)
  JWT_SECRET=$(rand 64)
  AGENT_TOKEN=$(rand 32)
  ADMIN_PASSWORD=$(rand 16)

  _replace() {
    local key="$1" val="$2"
    if grep -q "^${key}=" .env; then
      _sed_inplace "s|^${key}=.*|${key}=${val}|" .env
    else
      echo "${key}=${val}" >> .env
    fi
  }
  _replace POSTGRES_PASSWORD    "$POSTGRES_PASSWORD"
  _replace JWT_SECRET           "$JWT_SECRET"
  _replace AGENT_REGISTER_TOKEN "$AGENT_TOKEN"
  _replace ADMIN_PASSWORD       "$ADMIN_PASSWORD"
  _replace FRONTEND_PORT        "$FRONTEND_PORT"
  _replace ENVIRONMENT          production

  # 凭据存档（mode 600）
  cat > .deploy-credentials.txt <<CRED
# NightMend 首次部署生成的凭据 · $(date -u +"%Y-%m-%d %H:%M:%S UTC")
# ⚠️ 本文件包含初始凭据 · 妥善保管 · 首次登录改密后可删除

Admin email     : admin@nightmend.local
Admin password  : ${ADMIN_PASSWORD}

Postgres pwd    : ${POSTGRES_PASSWORD}
JWT secret      : ${JWT_SECRET}
Agent token     : ${AGENT_TOKEN}
Front port      : ${FRONTEND_PORT}
CRED
  chmod 600 .deploy-credentials.txt
  ok "已生成 .env 和 .deploy-credentials.txt (mode 600)"
fi

# ── 镜像 ───────────────────────────────────────────────
step "2/6 · 准备镜像"
if [ "$SKIP_PULL" = false ]; then
  $COMPOSE pull
else
  info "--skip-pull · 跳过拉镜像"
fi

# ── 启动 ───────────────────────────────────────────────
step "3/6 · 启动服务"
$COMPOSE up -d

# ── 等就绪 ──────────────────────────────────────────────
step "4/6 · 等后端就绪"
_wait_healthy || true

# ── migration ─────────────────────────────────────────
step "5/6 · 数据库初始化"
$COMPOSE exec -T backend alembic upgrade head || warn "alembic 失败 · 检查 backend 日志"

if [ "$SEED_DEMO" = true ]; then
  info "塞入 demo 数据（跳过用 --no-seed）"
  $COMPOSE exec -T backend python -m app.scripts.seed_demo >/dev/null 2>&1 || \
    warn "demo 数据塞入失败（不影响核心功能）"
fi

# ── 收尾 ───────────────────────────────────────────────
step "6/6 · 完成"
_print_access
