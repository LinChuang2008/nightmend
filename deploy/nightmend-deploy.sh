#!/usr/bin/env bash
# NightMend 一键部署脚本
# https://github.com/LinChuang2008/nightmend
set -euo pipefail

# ─── 版本 ───────────────────────────────────────────────
SCRIPT_VERSION="1.0.0"
NIGHTMEND_DIR="/opt/nightmend"
COMPOSE_FILE="docker-compose.prod.yml"
REPO_URL="https://github.com/LinChuang2008/nightmend.git"

# ─── 颜色 ───────────────────────────────────────────────
if [ -t 1 ] && command -v tput &>/dev/null && [ "$(tput colors 2>/dev/null || echo 0)" -ge 8 ]; then
  RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
  BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
else
  RED=''; GREEN=''; YELLOW=''; BLUE=''; CYAN=''; BOLD=''; NC=''
fi

# ─── 辅助函数 ───────────────────────────────────────────
info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "\n${CYAN}${BOLD}▶ Step $1: $2${NC}"; }
die()   { err "$@"; exit 1; }

# ─── 默认参数 ───────────────────────────────────────────
DOMAIN=""
AI_KEY=""
AI_MODEL="deepseek-chat"
AI_BASE="https://api.deepseek.com/v1"
FRONTEND_PORT="3001"
BACKEND_PORT="8001"
ENABLE_SSL=false
WITH_AGENT=false
INSTALL_DIR="$NIGHTMEND_DIR"

# ─── 参数解析 ───────────────────────────────────────────
usage() {
  cat <<EOF
${BOLD}NightMend 一键部署脚本 v${SCRIPT_VERSION}${NC}

用法: $0 [选项]

选项:
  --domain <域名>        访问域名或 IP（默认: 自动检测公网 IP）
  --ai-key <key>         AI API Key（DeepSeek/OpenAI 兼容）
  --ai-model <model>     AI 模型名称（默认: deepseek-chat）
  --ai-base <url>        AI API 基础 URL（默认: https://api.deepseek.com/v1）
  --port <端口>          前端端口（默认: 3001）
  --backend-port <端口>  后端端口（默认: 8001）
  --ssl                  启用 SSL（需要域名）
  --with-agent           同时安装监控 Agent
  --install-dir <目录>   安装目录（默认: /opt/nightmend）
  -h, --help             显示帮助

示例:
  # 最简安装
  sudo bash $0

  # 指定域名和 AI
  sudo bash $0 --domain monitor.example.com --ai-key sk-xxxx

  # 自定义端口 + Agent
  sudo bash $0 --port 80 --backend-port 8080 --with-agent
EOF
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain)        DOMAIN="$2"; shift 2 ;;
    --ai-key)        AI_KEY="$2"; shift 2 ;;
    --ai-model)      AI_MODEL="$2"; shift 2 ;;
    --ai-base)       AI_BASE="$2"; shift 2 ;;
    --port)          FRONTEND_PORT="$2"; shift 2 ;;
    --backend-port)  BACKEND_PORT="$2"; shift 2 ;;
    --ssl)           ENABLE_SSL=true; shift ;;
    --with-agent)    WITH_AGENT=true; shift ;;
    --install-dir)   INSTALL_DIR="$2"; shift 2 ;;
    -h|--help)       usage ;;
    *) die "未知参数: $1\n运行 $0 --help 查看帮助" ;;
  esac
done

# ─── 前置检查 ───────────────────────────────────────────
[[ $EUID -eq 0 ]] || die "请使用 root 权限运行: sudo bash $0"

step 1 "检测操作系统"

detect_os() {
  if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="${ID:-unknown}"
    OS_VERSION="${VERSION_ID:-unknown}"
    OS_NAME="${PRETTY_NAME:-unknown}"
  else
    die "无法检测操作系统，需要 /etc/os-release"
  fi

  case "$OS_ID" in
    ubuntu)
      [[ "$OS_VERSION" =~ ^(22|24) ]] || warn "未测试的 Ubuntu 版本: $OS_VERSION（推荐 22.04/24.04）"
      PKG_MANAGER="apt-get"
      ;;
    debian)
      [[ "$OS_VERSION" =~ ^12 ]] || warn "未测试的 Debian 版本: $OS_VERSION（推荐 12）"
      PKG_MANAGER="apt-get"
      ;;
    centos|rhel|rocky|almalinux)
      PKG_MANAGER="dnf"
      ;;
    *)
      warn "未测试的操作系统: $OS_NAME，将尝试继续..."
      PKG_MANAGER="apt-get"
      ;;
  esac
  ok "操作系统: $OS_NAME ($OS_ID $OS_VERSION)"
}
detect_os

# ─── Docker 安装 ──────────────────────────────────────
step 2 "检测 / 安装 Docker"

install_docker() {
  if command -v docker &>/dev/null; then
    DOCKER_VER=$(docker --version | grep -oP '\d+\.\d+\.\d+' | head -1)
    ok "Docker 已安装: $DOCKER_VER"
  else
    info "安装 Docker..."
    if [ "$PKG_MANAGER" = "apt-get" ]; then
      apt-get update -qq
      apt-get install -y -qq ca-certificates curl gnupg
      install -m 0755 -d /etc/apt/keyrings
      curl -fsSL "https://download.docker.com/linux/$OS_ID/gpg" | gpg --dearmor -o /etc/apt/keyrings/docker.gpg 2>/dev/null
      chmod a+r /etc/apt/keyrings/docker.gpg
      echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/$OS_ID $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
      apt-get update -qq
      apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    else
      dnf install -y -q dnf-plugins-core
      dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
      dnf install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
    fi
    systemctl enable --now docker
    ok "Docker 安装完成"
  fi

  # 检查 Docker Compose
  if docker compose version &>/dev/null; then
    ok "Docker Compose 可用: $(docker compose version --short 2>/dev/null || echo 'v2')"
  else
    die "Docker Compose 不可用，请安装 docker-compose-plugin"
  fi
}
install_docker

# ─── 检测域名 / IP ──────────────────────────────────────
step 3 "检测访问地址"

if [ -z "$DOMAIN" ]; then
  DOMAIN=$(curl -s --max-time 5 https://ifconfig.me 2>/dev/null || curl -s --max-time 5 https://ipinfo.io/ip 2>/dev/null || hostname -I | awk '{print $1}')
  info "自动检测地址: $DOMAIN"
fi
[ -n "$DOMAIN" ] || die "无法检测公网 IP，请使用 --domain 指定"
ok "访问地址: $DOMAIN"

# ─── 准备安装目录 ──────────────────────────────────────
step 4 "准备项目文件"

mkdir -p "$INSTALL_DIR"

if [ -d "$INSTALL_DIR/.git" ]; then
  info "项目已存在，拉取最新代码..."
  cd "$INSTALL_DIR"
  git pull --quiet 2>/dev/null || warn "git pull 失败，使用现有代码"
elif [ -d "$INSTALL_DIR/backend" ] && [ -d "$INSTALL_DIR/frontend" ]; then
  info "项目文件已存在（非 git），跳过克隆"
  cd "$INSTALL_DIR"
else
  info "克隆 NightMend 仓库..."
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR" 2>/dev/null || die "克隆仓库失败，请检查网络"
  cd "$INSTALL_DIR"
fi
ok "项目目录: $INSTALL_DIR"

# ─── 生成 .env ────────────────────────────────────────
step 5 "生成配置文件"

ENV_FILE="$INSTALL_DIR/.env"

generate_secret() {
  openssl rand -base64 "$1" 2>/dev/null | tr -d '/+=' | head -c "$1"
}

if [ -f "$ENV_FILE" ]; then
  info ".env 文件已存在，保留现有配置"
  # 读取现有值用于后续输出
  source "$ENV_FILE" 2>/dev/null || true
else
  DB_PASSWORD=$(generate_secret 32)
  JWT_SECRET=$(generate_secret 48)
  ADMIN_PASSWORD=$(generate_secret 16)

  cat > "$ENV_FILE" <<ENVEOF
# NightMend 生产环境配置
# 由 nightmend-deploy.sh v${SCRIPT_VERSION} 自动生成于 $(date '+%Y-%m-%d %H:%M:%S')

# ---------- 数据库 ----------
POSTGRES_DB=nightmend
POSTGRES_USER=nightmend
POSTGRES_PASSWORD=${DB_PASSWORD}

# ---------- JWT ----------
JWT_SECRET_KEY=${JWT_SECRET}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=120
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ---------- AI ----------
AI_PROVIDER=deepseek
AI_API_KEY=${AI_KEY}
AI_API_BASE=${AI_BASE}
AI_MODEL=${AI_MODEL}
AI_MAX_TOKENS=2000
AI_AUTO_SCAN=false

# ---------- 记忆系统 ----------
MEMORY_ENABLED=false
MEMORY_API_URL=

# ---------- 自动修复 ----------
AGENT_ENABLED=false
AGENT_DRY_RUN=true
AGENT_MAX_AUTO_PER_HOUR=10
AGENT_NOTIFY_ON_SUCCESS=true
AGENT_NOTIFY_ON_FAILURE=true

# ---------- 端口 ----------
FRONTEND_PORT=${FRONTEND_PORT}
BACKEND_PORT=${BACKEND_PORT}

# ---------- 管理员 ----------
ADMIN_PASSWORD=${ADMIN_PASSWORD}
ENVEOF

  chmod 600 "$ENV_FILE"
  ok "配置文件已生成: $ENV_FILE"
fi

# 确保变量可用
source "$ENV_FILE" 2>/dev/null || true

# ─── 复制 compose 文件 ────────────────────────────────
COMPOSE_SRC="$INSTALL_DIR/deploy/$COMPOSE_FILE"
COMPOSE_DST="$INSTALL_DIR/$COMPOSE_FILE"

if [ -f "$COMPOSE_SRC" ]; then
  cp "$COMPOSE_SRC" "$COMPOSE_DST"
  ok "compose 文件已就绪"
else
  warn "deploy/$COMPOSE_FILE 不存在，请确认仓库包含此文件"
  die "缺少 $COMPOSE_FILE"
fi

# ─── Docker 镜像获取 & 启动 ──────────────────────────
step 6 "获取镜像并启动服务"

cd "$INSTALL_DIR"

GHCR_BACKEND="ghcr.io/linchuang2008/nightmend-backend:latest"
GHCR_FRONTEND="ghcr.io/linchuang2008/nightmend-frontend:latest"

pull_or_build() {
  info "尝试从 GHCR 拉取预构建镜像..."
  if docker pull "$GHCR_BACKEND" 2>/dev/null && docker pull "$GHCR_FRONTEND" 2>/dev/null; then
    ok "镜像拉取成功（跳过本地构建）"
    return 0
  else
    warn "GHCR 拉取失败，回退到本地构建..."
    if [ -d "$INSTALL_DIR/backend" ] && [ -d "$INSTALL_DIR/frontend" ]; then
      info "构建 Docker 镜像（首次可能需要几分钟）..."
      docker build -t "$GHCR_BACKEND" "$INSTALL_DIR/backend" 2>&1 | tail -3
      docker build -t "$GHCR_FRONTEND" "$INSTALL_DIR/frontend" 2>&1 | tail -3
      ok "本地构建完成"
    else
      die "无法拉取镜像且缺少源码，无法继续"
    fi
  fi
}

pull_or_build

info "启动容器..."
docker compose -f "$COMPOSE_FILE" up -d

ok "容器已启动"

# ─── 健康检查 ──────────────────────────────────────────
step 7 "等待服务就绪"

HEALTH_TIMEOUT=120
HEALTH_INTERVAL=5
ELAPSED=0

while [ $ELAPSED -lt $HEALTH_TIMEOUT ]; do
  # 检查后端是否响应
  if curl -sf --max-time 3 "http://localhost:${BACKEND_PORT:-8001}/docs" &>/dev/null; then
    ok "后端服务就绪 (${ELAPSED}s)"
    break
  fi
  sleep "$HEALTH_INTERVAL"
  ELAPSED=$((ELAPSED + HEALTH_INTERVAL))
  printf "  等待中... %ds / %ds\r" "$ELAPSED" "$HEALTH_TIMEOUT"
done

if [ $ELAPSED -ge $HEALTH_TIMEOUT ]; then
  warn "后端服务超时 (${HEALTH_TIMEOUT}s)，请手动检查:"
  echo "  docker compose -f $COMPOSE_FILE logs backend"
else
  # 检查前端
  if curl -sf --max-time 3 "http://localhost:${FRONTEND_PORT:-3001}" &>/dev/null; then
    ok "前端服务就绪"
  else
    warn "前端未响应，请手动检查"
  fi
fi

# ─── 创建管理员 ───────────────────────────────────────
step 8 "创建管理员账号"

ADMIN_USER="admin"
ADMIN_PASS="${ADMIN_PASSWORD:-$(generate_secret 16)}"

# 尝试注册管理员（如果已存在会返回错误，这是正常的）
REGISTER_RESP=$(curl -sf --max-time 10 \
  -X POST "http://localhost:${BACKEND_PORT:-8001}/api/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASS}\",\"email\":\"admin@nightmend.local\",\"role\":\"admin\"}" \
  2>/dev/null || echo '{"error":"failed"}')

if echo "$REGISTER_RESP" | grep -q '"id"'; then
  ok "管理员账号已创建"
elif echo "$REGISTER_RESP" | grep -qi 'exist'; then
  info "管理员账号已存在，跳过"
else
  warn "创建管理员可能失败，请手动创建或检查日志"
fi

# ─── Agent 安装 ──────────────────────────────────────
if $WITH_AGENT; then
  step 9 "安装监控 Agent"

  if command -v pip3 &>/dev/null || command -v pip &>/dev/null; then
    PIP_CMD=$(command -v pip3 || command -v pip)
  else
    info "安装 Python pip..."
    if [ "$PKG_MANAGER" = "apt-get" ]; then
      apt-get install -y -qq python3-pip
    else
      dnf install -y -q python3-pip
    fi
    PIP_CMD=$(command -v pip3 || command -v pip)
  fi

  AGENT_DIR="$INSTALL_DIR/agent"
  if [ -d "$AGENT_DIR" ] && [ -f "$AGENT_DIR/pyproject.toml" ]; then
    info "从本地安装 Agent..."
    $PIP_CMD install -q "$AGENT_DIR"
  else
    info "从仓库安装 Agent..."
    $PIP_CMD install -q "git+${REPO_URL}#subdirectory=agent" || warn "Agent 安装失败"
  fi

  # 创建 Agent 配置
  AGENT_CONFIG_DIR="/etc/nightmend"
  mkdir -p "$AGENT_CONFIG_DIR"
  cat > "$AGENT_CONFIG_DIR/agent.conf" <<AGENTEOF
[server]
url = http://localhost:${BACKEND_PORT:-8001}
# token = <在 Web 界面创建 Agent Token 后填入>

[collector]
interval = 60

[log]
level = INFO
AGENTEOF

  ok "Agent 已安装，配置文件: $AGENT_CONFIG_DIR/agent.conf"
  warn "请在 Web 界面创建 Agent Token，并填入 $AGENT_CONFIG_DIR/agent.conf"
else
  info "跳过 Agent 安装（使用 --with-agent 启用）"
fi

# ─── 安装摘要 ──────────────────────────────────────────
STEP_NUM=9
$WITH_AGENT && STEP_NUM=10
step $STEP_NUM "安装完成"

PROTO="http"
$ENABLE_SSL && PROTO="https"

cat <<SUMMARY

${GREEN}${BOLD}╔══════════════════════════════════════════════════════╗
║          NightMend 安装成功！                          ║
╚══════════════════════════════════════════════════════╝${NC}

  ${BOLD}访问地址:${NC}    ${PROTO}://${DOMAIN}:${FRONTEND_PORT}
  ${BOLD}后端 API:${NC}    ${PROTO}://${DOMAIN}:${BACKEND_PORT}
  ${BOLD}管理员账号:${NC}  ${ADMIN_USER}
  ${BOLD}管理员密码:${NC}  ${ADMIN_PASS}
  ${BOLD}安装目录:${NC}    ${INSTALL_DIR}
  ${BOLD}配置文件:${NC}    ${INSTALL_DIR}/.env

SUMMARY

if [ -n "$AI_KEY" ]; then
  echo -e "  ${BOLD}AI 功能:${NC}     ✅ 已配置 ($AI_MODEL)"
else
  echo -e "  ${BOLD}AI 功能:${NC}     ⚠️  未配置（在 .env 中设置 AI_API_KEY）"
fi

$WITH_AGENT && echo -e "  ${BOLD}Agent:${NC}       ✅ 已安装（需配置 Token）"

cat <<TIPS

${YELLOW}${BOLD}常用命令:${NC}
  cd $INSTALL_DIR
  docker compose -f $COMPOSE_FILE logs -f        # 查看日志
  docker compose -f $COMPOSE_FILE ps             # 查看状态
  docker compose -f $COMPOSE_FILE restart         # 重启服务
  docker compose -f $COMPOSE_FILE down            # 停止服务

${YELLOW}${BOLD}安全提醒:${NC}
  1. 请尽快修改管理员默认密码
  2. 建议配置防火墙，仅开放 ${FRONTEND_PORT} 和 ${BACKEND_PORT} 端口
  3. 生产环境建议配置 Nginx 反向代理 + SSL

TIPS

echo -e "${GREEN}感谢使用 NightMend！如有问题请访问 https://github.com/LinChuang2008/nightmend${NC}"
