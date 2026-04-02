#!/usr/bin/env bash
# NightMend 一键部署脚本
# 用法: curl -sSL https://get.nightmend.io/install.sh | bash
# 升级: curl -sSL https://get.nightmend.io/install.sh | bash -s -- --upgrade
set -euo pipefail

# ── 颜色 ──────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }
die()   { err "$*"; exit 1; }

# ── 参数 ──────────────────────────────────────────────
UPGRADE=false
INSTALL_DIR="/opt/nightmend"
REPO_URL="https://github.com/LinChuang2008/nightmend.git"
BRANCH="main"

for arg in "$@"; do
  case "$arg" in
    --upgrade)  UPGRADE=true ;;
    --dir=*)    INSTALL_DIR="${arg#*=}" ;;
    --branch=*) BRANCH="${arg#*=}" ;;
    --help|-h)
      echo "Usage: install.sh [--upgrade] [--dir=/opt/nightmend] [--branch=main]"
      exit 0 ;;
  esac
done

# ── 权限检查 ───────────────────────────────────────────
if [ "$(id -u)" -ne 0 ]; then
  die "请使用 root 用户或 sudo 运行此脚本"
fi

# ── OS 检测 ────────────────────────────────────────────
detect_os() {
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="${ID}"
    OS_VERSION="${VERSION_ID:-unknown}"
  else
    die "无法检测操作系统，仅支持 CentOS/Ubuntu/Debian"
  fi

  case "$OS_ID" in
    centos|rhel|rocky|almalinux|fedora) OS_FAMILY="rhel" ;;
    ubuntu|debian)                       OS_FAMILY="debian" ;;
    *)                                   die "不支持的操作系统: $OS_ID" ;;
  esac
  ok "操作系统: $OS_ID $OS_VERSION ($OS_FAMILY)"
}

# ── Docker 检测/安装 ──────────────────────────────────
ensure_docker() {
  if command -v docker &>/dev/null; then
    ok "Docker 已安装: $(docker --version)"
  else
    info "正在安装 Docker..."
    if ! curl -fsSL https://get.docker.com | bash; then
      die "Docker 安装失败，请手动安装后重试"
    fi
    systemctl enable --now docker
    ok "Docker 安装完成"
  fi

  # docker compose 检查
  if docker compose version &>/dev/null; then
    ok "Docker Compose 可用: $(docker compose version --short)"
  elif command -v docker-compose &>/dev/null; then
    die "检测到旧版 docker-compose，请升级到 Docker Compose V2"
  else
    die "Docker Compose 不可用，请安装 Docker Compose V2"
  fi
}

# ── 端口检查 ───────────────────────────────────────────
check_port() {
  local port=$1 name=$2
  if ss -tlnp 2>/dev/null | grep -q ":${port} " || \
     netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
    warn "端口 $port ($name) 已被占用"
    return 1
  fi
  return 0
}

# ── 随机字符串生成 ─────────────────────────────────────
rand_string() {
  local len=${1:-32}
  tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$len" 2>/dev/null || \
    openssl rand -hex "$((len/2))" 2>/dev/null || \
    date +%s%N | sha256sum | head -c "$len"
}

# ── 交互式配置 ────────────────────────────────────────
configure() {
  # 默认端口
  BACKEND_PORT=8001
  FRONTEND_PORT=3001
  POSTGRES_PORT=5433
  REDIS_PORT=6380

  echo ""
  echo -e "${BLUE}═══════════════════════════════════════════${NC}"
  echo -e "${BLUE}       NightMend 部署配置向导${NC}"
  echo -e "${BLUE}═══════════════════════════════════════════${NC}"
  echo ""

  # 端口配置
  read -rp "是否修改默认端口？(y/N): " change_ports
  if [[ "$change_ports" =~ ^[Yy]$ ]]; then
    read -rp "后端端口 [${BACKEND_PORT}]: "  input; BACKEND_PORT="${input:-$BACKEND_PORT}"
    read -rp "前端端口 [${FRONTEND_PORT}]: " input; FRONTEND_PORT="${input:-$FRONTEND_PORT}"
    read -rp "PostgreSQL 端口 [${POSTGRES_PORT}]: " input; POSTGRES_PORT="${input:-$POSTGRES_PORT}"
    read -rp "Redis 端口 [${REDIS_PORT}]: " input; REDIS_PORT="${input:-$REDIS_PORT}"
  fi

  # 检查端口占用
  local port_ok=true
  for pair in "BACKEND_PORT:后端" "FRONTEND_PORT:前端" "POSTGRES_PORT:PostgreSQL" "REDIS_PORT:Redis"; do
    local var="${pair%%:*}" name="${pair#*:}"
    if ! check_port "${!var}" "$name"; then
      port_ok=false
    fi
  done
  if [ "$port_ok" = false ]; then
    read -rp "部分端口已占用，是否继续？(y/N): " cont
    [[ "$cont" =~ ^[Yy]$ ]] || die "请修改端口后重试"
  fi

  # DeepSeek API Key
  echo ""
  read -rp "输入 DeepSeek API Key（回车跳过，AI 功能将不可用）: " AI_API_KEY
  AI_API_KEY="${AI_API_KEY:-}"

  # 生成安全凭证
  JWT_SECRET_KEY="$(rand_string 48)"
  POSTGRES_PASSWORD="$(rand_string 24)"

  ok "配置完成"
}

# ── 生成 .env ─────────────────────────────────────────
generate_env() {
  local env_file="${INSTALL_DIR}/.env"

  # 幂等：如果 .env 已存在，保留已有密码
  if [ -f "$env_file" ]; then
    warn ".env 已存在，保留现有安全凭证"
    # 读取已有值
    existing_jwt=$(grep -oP '^JWT_SECRET_KEY=\K.*' "$env_file" 2>/dev/null || true)
    existing_dbpw=$(grep -oP '^POSTGRES_PASSWORD=\K.*' "$env_file" 2>/dev/null || true)
    existing_ai=$(grep -oP '^AI_API_KEY=\K.*' "$env_file" 2>/dev/null || true)
    JWT_SECRET_KEY="${existing_jwt:-$JWT_SECRET_KEY}"
    POSTGRES_PASSWORD="${existing_dbpw:-$POSTGRES_PASSWORD}"
    # 只在用户本次输入了新 key 时覆盖
    if [ -z "$AI_API_KEY" ]; then
      AI_API_KEY="${existing_ai:-}"
    fi
  fi

  cat > "$env_file" <<EOF
# NightMend 环境配置 - 由 install.sh 自动生成
# 生成时间: $(date '+%Y-%m-%d %H:%M:%S')

# ---- 数据库 ----
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=nightmend
POSTGRES_USER=nightmend
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}

# ---- Redis ----
REDIS_HOST=redis
REDIS_PORT=6379

# ---- JWT 认证 ----
JWT_SECRET_KEY=${JWT_SECRET_KEY}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=120
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ---- 后端服务 ----
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# ---- 端口映射（宿主机）----
HOST_BACKEND_PORT=${BACKEND_PORT}
HOST_FRONTEND_PORT=${FRONTEND_PORT}
HOST_POSTGRES_PORT=${POSTGRES_PORT}
HOST_REDIS_PORT=${REDIS_PORT}

# ---- AI 配置 ----
AI_PROVIDER=deepseek
AI_API_KEY=${AI_API_KEY}
AI_API_BASE=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat
AI_MAX_TOKENS=2000
AI_AUTO_SCAN=false
EOF

  chmod 600 "$env_file"
  ok ".env 已生成"
}

# ── 生成 docker-compose.override.yml（端口映射）──────
generate_compose_override() {
  local override="${INSTALL_DIR}/docker-compose.override.yml"
  cat > "$override" <<EOF
# 由 install.sh 自动生成 - 自定义端口映射
services:
  postgres:
    ports:
      - "${POSTGRES_PORT}:5432"
  redis:
    ports:
      - "${REDIS_PORT}:6379"
  backend:
    ports:
      - "${BACKEND_PORT}:8000"
  frontend:
    ports:
      - "${FRONTEND_PORT}:80"
EOF
  ok "端口映射配置已生成"
}

# ── 拉取代码 ──────────────────────────────────────────
fetch_code() {
  if [ -d "${INSTALL_DIR}/.git" ]; then
    info "更新代码..."
    cd "$INSTALL_DIR"
    git fetch origin "$BRANCH" --depth=1 || die "代码更新失败，请检查网络"
    git reset --hard "origin/$BRANCH"
    ok "代码已更新"
  else
    info "克隆代码仓库..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone --depth=1 --branch "$BRANCH" "$REPO_URL" "$INSTALL_DIR" || \
      die "代码克隆失败，请检查网络和仓库地址"
    cd "$INSTALL_DIR"
    ok "代码已克隆到 $INSTALL_DIR"
  fi
}

# ── 启动服务 ──────────────────────────────────────────
start_services() {
  cd "$INSTALL_DIR"
  info "构建并启动容器..."
  docker compose build --pull || die "容器构建失败"
  docker compose up -d || die "容器启动失败"
  ok "容器已启动"
}

# ── 安装后验证 ────────────────────────────────────────
verify() {
  info "等待服务就绪..."
  local max_wait=60
  local waited=0

  # 等待所有容器健康
  while [ $waited -lt $max_wait ]; do
    local all_up=true
    for svc in postgres redis backend frontend; do
      local status
      status=$(docker compose -f "${INSTALL_DIR}/docker-compose.yml" ps --format json 2>/dev/null | \
        grep -o "\"$svc\"" || echo "")
      if [ -z "$status" ]; then
        all_up=false
        break
      fi
    done

    # 尝试 API 请求
    if curl -sf "http://127.0.0.1:${BACKEND_PORT}/docs" -o /dev/null 2>/dev/null; then
      break
    fi

    sleep 3
    waited=$((waited + 3))
    printf "."
  done
  echo ""

  # 检查各容器状态
  local failed=false
  cd "$INSTALL_DIR"
  for svc in postgres redis backend frontend; do
    if docker compose ps "$svc" 2>/dev/null | grep -q "Up\|running"; then
      ok "$svc 运行正常"
    else
      err "$svc 未正常运行"
      failed=true
    fi
  done

  # API 检查
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/docs" -o /dev/null 2>/dev/null; then
    ok "后端 API 可访问"
  else
    warn "后端 API 暂时无法访问，可能仍在启动中"
  fi

  if [ "$failed" = true ]; then
    warn "部分服务未就绪，请稍后检查: docker compose -f ${INSTALL_DIR}/docker-compose.yml ps"
  fi
}

# ── 输出结果 ──────────────────────────────────────────
print_result() {
  local host_ip
  host_ip=$(hostname -I 2>/dev/null | awk '{print $1}' || curl -sf ifconfig.me || echo "YOUR_SERVER_IP")

  echo ""
  echo -e "${GREEN}═══════════════════════════════════════════${NC}"
  echo -e "${GREEN}       NightMend 部署完成！${NC}"
  echo -e "${GREEN}═══════════════════════════════════════════${NC}"
  echo ""
  echo -e "  前端访问:  ${BLUE}http://${host_ip}:${FRONTEND_PORT}${NC}"
  echo -e "  后端 API:  ${BLUE}http://${host_ip}:${BACKEND_PORT}${NC}"
  echo -e "  API 文档:  ${BLUE}http://${host_ip}:${BACKEND_PORT}/docs${NC}"
  echo ""
  echo -e "  默认账号:  ${YELLOW}admin${NC}"
  echo -e "  默认密码:  ${YELLOW}admin123${NC}"
  echo ""
  if [ -z "$AI_API_KEY" ]; then
    echo -e "  ${YELLOW}AI 功能未启用（未配置 DeepSeek API Key）${NC}"
    echo -e "  如需启用，编辑 ${INSTALL_DIR}/.env 中的 AI_API_KEY"
    echo ""
  fi
  echo -e "  安装目录:  ${INSTALL_DIR}"
  echo -e "  查看日志:  docker compose -f ${INSTALL_DIR}/docker-compose.yml logs -f"
  echo -e "  升级方法:  curl -sSL https://get.nightmend.io/install.sh | bash -s -- --upgrade"
  echo ""
  echo -e "  ${RED}⚠ 请立即修改默认密码！${NC}"
  echo ""
}

# ── 升级流程 ──────────────────────────────────────────
do_upgrade() {
  info "开始升级 NightMend..."

  if [ ! -d "${INSTALL_DIR}/.git" ]; then
    die "未找到安装目录 ${INSTALL_DIR}，请先执行全新安装"
  fi

  # 读取现有端口配置
  if [ -f "${INSTALL_DIR}/.env" ]; then
    BACKEND_PORT=$(grep -oP '^HOST_BACKEND_PORT=\K.*' "${INSTALL_DIR}/.env" 2>/dev/null || echo "8001")
    FRONTEND_PORT=$(grep -oP '^HOST_FRONTEND_PORT=\K.*' "${INSTALL_DIR}/.env" 2>/dev/null || echo "3001")
    POSTGRES_PORT=$(grep -oP '^HOST_POSTGRES_PORT=\K.*' "${INSTALL_DIR}/.env" 2>/dev/null || echo "5433")
    REDIS_PORT=$(grep -oP '^HOST_REDIS_PORT=\K.*' "${INSTALL_DIR}/.env" 2>/dev/null || echo "6380")
  fi

  fetch_code

  # 不重新生成 .env，保留所有现有配置
  cd "$INSTALL_DIR"
  info "重建容器（保留数据卷）..."
  docker compose build --pull
  docker compose up -d
  ok "升级完成"

  verify
  print_result
}

# ── 主流程 ────────────────────────────────────────────
main() {
  echo ""
  echo -e "${BLUE}╔═══════════════════════════════════════════╗${NC}"
  echo -e "${BLUE}║     NightMend 一键部署脚本 v1.0          ║${NC}"
  echo -e "${BLUE}║     开源运维监控平台                     ║${NC}"
  echo -e "${BLUE}╚═══════════════════════════════════════════╝${NC}"
  echo ""

  if [ "$UPGRADE" = true ]; then
    do_upgrade
    exit 0
  fi

  detect_os
  ensure_docker
  configure
  fetch_code
  generate_env
  generate_compose_override
  start_services
  verify
  print_result
}

main "$@"
