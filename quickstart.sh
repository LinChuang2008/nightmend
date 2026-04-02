#!/usr/bin/env bash
# NightMend 5分钟快速启动脚本
# 目标：让新用户零配置快速体验 NightMend
# 用法：bash quickstart.sh [--no-ai] [--port-offset=100]

set -euo pipefail

# ── 颜色和样式 ──────────────────────────────────────────
RED='\033[0;31m'    # 错误
GREEN='\033[0;32m'  # 成功  
YELLOW='\033[1;33m' # 警告
BLUE='\033[0;34m'   # 信息
CYAN='\033[0;36m'   # 提示
BOLD='\033[1m'      # 粗体
NC='\033[0m'        # 无颜色

# ── 输出函数 ────────────────────────────────────────────
info()  { echo -e "${BLUE}ℹ️  ${NC}$*"; }
ok()    { echo -e "${GREEN}✅ ${NC}$*"; }
warn()  { echo -e "${YELLOW}⚠️  ${NC}$*"; }
error() { echo -e "${RED}❌ ${NC}$*"; }
step()  { echo -e "\n${CYAN}🚀 ${BOLD}$*${NC}"; }
success() { echo -e "\n${GREEN}${BOLD}🎉 $*${NC}"; }

# ── 参数解析 ────────────────────────────────────────────
SKIP_AI=false
PORT_OFFSET=0
DRY_RUN=false

for arg in "$@"; do
    case "$arg" in
        --no-ai)        SKIP_AI=true ;;
        --port-offset=*) PORT_OFFSET="${arg#*=}" ;;
        --dry-run)      DRY_RUN=true ;;
        --help|-h)
            cat << 'EOF'
🚀 NightMend 快速启动脚本

用法: bash quickstart.sh [选项]

选项:
  --no-ai              跳过 AI 功能配置
  --port-offset=N      端口偏移（避免冲突）
  --dry-run            仅检查环境，不启动服务
  -h, --help           显示此帮助

示例:
  bash quickstart.sh                    # 标准启动
  bash quickstart.sh --no-ai            # 跳过AI配置  
  bash quickstart.sh --port-offset=100  # 端口+100避免冲突

EOF
            exit 0
            ;;
    esac
done

# ── 全局变量 ────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
START_TIME=$(date +%s)
LOG_FILE="${SCRIPT_DIR}/quickstart.log"

# 默认端口
DEFAULT_FRONTEND_PORT=$((3001 + PORT_OFFSET))
DEFAULT_BACKEND_PORT=$((8001 + PORT_OFFSET))  
DEFAULT_POSTGRES_PORT=$((5433 + PORT_OFFSET))
DEFAULT_REDIS_PORT=$((6380 + PORT_OFFSET))

# 分配的端口（动态调整）
FRONTEND_PORT=$DEFAULT_FRONTEND_PORT
BACKEND_PORT=$DEFAULT_BACKEND_PORT
POSTGRES_PORT=$DEFAULT_POSTGRES_PORT
REDIS_PORT=$DEFAULT_REDIS_PORT

# ── 日志记录 ────────────────────────────────────────────
log() {
    echo "[$(date '+%H:%M:%S')] $*" >> "$LOG_FILE"
}

# ── 清理函数 ────────────────────────────────────────────
cleanup() {
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        echo ""
        error "启动失败，日志已保存到: $LOG_FILE"
        warn "可尝试重新运行或查看日志排查问题"
        echo ""
        echo "🔍 快速诊断:"
        echo "   • 检查 Docker 是否正常运行: docker ps"
        echo "   • 查看容器状态: docker-compose ps" 
        echo "   • 查看服务日志: docker-compose logs"
    fi
    exit $exit_code
}
trap cleanup EXIT

# ── 环境检查函数 ────────────────────────────────────────

# 检查命令是否存在
check_command() {
    local cmd=$1
    local name=${2:-$cmd}
    
    if command -v "$cmd" &>/dev/null; then
        ok "$name 已安装"
        return 0
    else
        return 1
    fi
}

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "linux"* ]]; then
        if command -v apt &>/dev/null; then
            echo "debian"
        elif command -v yum &>/dev/null || command -v dnf &>/dev/null; then
            echo "rhel"
        else
            echo "linux"
        fi
    elif [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "cygwin" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

# Docker 安装检查
check_docker() {
    step "检查 Docker 环境"
    
    if ! check_command docker "Docker"; then
        error "未发现 Docker，请先安装"
        echo ""
        case "$(detect_os)" in
            macos)
                echo "🍎 macOS 用户请执行:"
                echo "   brew install docker"
                echo "   或从 https://docker.com/desktop 下载 Docker Desktop"
                ;;
            debian)
                echo "🐧 Ubuntu/Debian 用户请执行:"
                echo "   curl -fsSL https://get.docker.com | bash"
                ;;
            rhel)
                echo "🐧 CentOS/RHEL 用户请执行:"
                echo "   curl -fsSL https://get.docker.com | bash"
                ;;
            *)
                echo "请访问 https://docs.docker.com/get-docker/ 安装 Docker"
                ;;
        esac
        echo ""
        exit 1
    fi
    
    # Docker Compose 检查
    if docker compose version &>/dev/null; then
        ok "Docker Compose 可用"
    elif command -v docker-compose &>/dev/null; then
        error "检测到旧版 docker-compose"  
        warn "请升级到 Docker Compose V2"
        echo "   官方文档: https://docs.docker.com/compose/install/"
        exit 1
    else
        error "Docker Compose 不可用"
        exit 1
    fi
    
    # Docker 守护进程检查
    if ! docker info &>/dev/null; then
        error "Docker 守护进程未运行"
        case "$(detect_os)" in
            macos)
                echo "请启动 Docker Desktop"
                ;;
            linux)
                echo "请执行: sudo systemctl start docker"
                ;;
        esac
        exit 1
    fi
    
    # 权限检查  
    if ! docker ps &>/dev/null; then
        warn "当前用户无 Docker 权限，将使用 sudo"
        if ! sudo docker ps &>/dev/null; then
            error "sudo 也无法访问 Docker"
            exit 1
        fi
        # 设置 sudo 别名
        shopt -s expand_aliases
        alias docker='sudo docker'
        alias docker-compose='sudo docker-compose'
    fi
    
    ok "Docker 环境检查通过"
}

# 端口检查和智能分配
check_ports() {
    step "检查端口占用"
    
    local ports_to_check=(
        "$FRONTEND_PORT:前端"
        "$BACKEND_PORT:后端" 
        "$POSTGRES_PORT:PostgreSQL"
        "$REDIS_PORT:Redis"
    )
    
    local conflicts=()
    
    for port_pair in "${ports_to_check[@]}"; do
        local port="${port_pair%:*}"
        local name="${port_pair#*:}"
        
        if lsof -ti :$port &>/dev/null || ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            conflicts+=("$port:$name")
        fi
    done
    
    if [ ${#conflicts[@]} -gt 0 ]; then
        warn "发现端口冲突:"
        for conflict in "${conflicts[@]}"; do
            local port="${conflict%:*}"
            local name="${conflict#*:}"
            echo "   • 端口 $port ($name) 已被占用"
        done
        
        info "正在自动分配新端口..."
        FRONTEND_PORT=$(find_free_port $DEFAULT_FRONTEND_PORT)
        BACKEND_PORT=$(find_free_port $DEFAULT_BACKEND_PORT)
        POSTGRES_PORT=$(find_free_port $DEFAULT_POSTGRES_PORT)
        REDIS_PORT=$(find_free_port $DEFAULT_REDIS_PORT)
        
        ok "已重新分配端口:"
        echo "   • 前端: $FRONTEND_PORT"
        echo "   • 后端: $BACKEND_PORT"
        echo "   • PostgreSQL: $POSTGRES_PORT"  
        echo "   • Redis: $REDIS_PORT"
    else
        ok "端口检查通过"
    fi
}

# 查找空闲端口
find_free_port() {
    local start_port=$1
    for port in $(seq $start_port $((start_port + 100))); do
        if ! lsof -ti :$port &>/dev/null && ! ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            echo $port
            return
        fi
    done
    error "无法找到空闲端口（起始: $start_port）"
    exit 1
}

# ── 配置生成函数 ────────────────────────────────────────

# 生成随机字符串
rand_string() {
    local len=${1:-32}
    openssl rand -hex $((len/2)) 2>/dev/null || \
    tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$len" || \
    date +%s%N | sha256sum | head -c "$len"
}

# 生成 .env 配置
generate_env() {
    step "生成配置文件"
    
    # 保留现有 AI Key（如果存在）
    local existing_ai_key=""
    if [ -f .env ]; then
        existing_ai_key=$(grep -oP '^AI_API_KEY=\K.*' .env 2>/dev/null || true)
        if [ -n "$existing_ai_key" ] && [ "$existing_ai_key" != "change-me" ]; then
            ok "保留现有 AI API Key"
        fi
    fi
    
    # 生成安全随机密钥
    local jwt_secret
    jwt_secret=$(rand_string 64)
    local postgres_password
    postgres_password="nightmend_$(rand_string 16)"
    
    # AI 配置
    local ai_key="$existing_ai_key"
    if [ -z "$ai_key" ] && [ "$SKIP_AI" = false ]; then
        echo ""
        info "AI 功能可提供智能运维分析（可选）"
        read -p "是否配置 DeepSeek API Key？(y/N): " configure_ai
        if [[ "$configure_ai" =~ ^[Yy]$ ]]; then
            echo "🔗 获取免费 API Key: https://platform.deepseek.com/api_keys"
            read -p "请输入 DeepSeek API Key: " ai_key
        fi
    fi
    
    # 写入配置文件
    cat > .env << EOF
# NightMend 快速启动配置 - 生成于 $(date)
# 🚀 由 quickstart.sh 自动生成，可手动调整

# ---- 数据库配置 ----
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=nightmend
POSTGRES_USER=nightmend
POSTGRES_PASSWORD=${postgres_password}

# ---- Redis 配置 ----
REDIS_HOST=redis
REDIS_PORT=6379

# ---- 认证配置 ----
JWT_SECRET_KEY=${jwt_secret}
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=120
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ---- 服务配置 ----
BACKEND_HOST=0.0.0.0
BACKEND_PORT=8000

# ---- 端口映射（宿主机）----
FRONTEND_PORT=${FRONTEND_PORT}
BACKEND_PORT=${BACKEND_PORT}
POSTGRES_PORT=${POSTGRES_PORT}
REDIS_PORT=${REDIS_PORT}

# ---- AI 功能配置 ----
AI_PROVIDER=deepseek
AI_API_KEY=${ai_key}
AI_API_BASE=https://api.deepseek.com/v1  
AI_MODEL=deepseek-chat
AI_MAX_TOKENS=2000
AI_AUTO_SCAN=false
EOF
    
    chmod 600 .env
    ok "配置文件已生成"
    
    if [ -z "$ai_key" ]; then
        info "AI 功能未启用，如需启用请编辑 .env 中的 AI_API_KEY"
    fi
}

# 生成端口映射覆盖
generate_port_override() {
    if [ ! -f docker-compose.yml ]; then
        warn "未找到 docker-compose.yml，跳过端口配置"
        return
    fi
    
    # 检查是否需要端口覆盖
    if [ "$FRONTEND_PORT" = "3001" ] && [ "$BACKEND_PORT" = "8001" ] && \
       [ "$POSTGRES_PORT" = "5433" ] && [ "$REDIS_PORT" = "6380" ]; then
        # 使用默认端口，不需要覆盖文件
        [ -f docker-compose.override.yml ] && rm -f docker-compose.override.yml
        return
    fi
    
    cat > docker-compose.override.yml << EOF
# 端口映射覆盖 - 自动生成
version: '3.8'
services:
  frontend:
    ports:
      - "${FRONTEND_PORT}:80"
  backend:
    ports:
      - "${BACKEND_PORT}:8000"
  postgres:
    ports:
      - "${POSTGRES_PORT}:5432"
  redis:
    ports:
      - "${REDIS_PORT}:6379"
EOF
    
    info "已生成端口映射配置"
}

# ── 服务管理函数 ────────────────────────────────────────

# 启动服务
start_services() {
    step "构建并启动服务"
    
    info "拉取基础镜像..."
    docker compose pull --quiet postgres redis 2>&1 | tee -a "$LOG_FILE" || true
    
    info "构建应用镜像..."
    docker compose build --pull --parallel 2>&1 | tee -a "$LOG_FILE"
    
    info "启动所有服务..."
    docker compose up -d 2>&1 | tee -a "$LOG_FILE"
    
    ok "服务启动完成"
}

# 等待服务就绪
wait_for_services() {
    step "等待服务就绪"
    
    local services=("postgres" "redis" "backend")
    local max_wait=120  # 2分钟超时
    local start_wait=$(date +%s)
    
    for service in "${services[@]}"; do
        info "检查 $service 服务..."
        
        case $service in
            postgres)
                wait_for_postgres
                ;;
            redis)
                wait_for_redis  
                ;;
            backend)
                wait_for_backend
                ;;
        esac
        
        if [ $? -eq 0 ]; then
            ok "$service 已就绪"
        else
            error "$service 启动超时"
            show_service_logs "$service"
            exit 1
        fi
        
        # 检查总超时
        local elapsed=$(( $(date +%s) - start_wait ))
        if [ $elapsed -gt $max_wait ]; then
            error "服务启动总时间超过 ${max_wait}s"
            exit 1
        fi
    done
    
    # 最终健康检查
    health_check
}

# PostgreSQL 就绪检查
wait_for_postgres() {
    local max_attempts=30
    local attempt=0
    
    until docker compose exec -T postgres pg_isready -U nightmend &>/dev/null; do
        sleep 2
        attempt=$((attempt + 1))
        if [ $attempt -gt $max_attempts ]; then
            return 1
        fi
    done
    return 0
}

# Redis 就绪检查  
wait_for_redis() {
    local max_attempts=30
    local attempt=0
    
    until docker compose exec -T redis redis-cli ping &>/dev/null; do
        sleep 2
        attempt=$((attempt + 1))
        if [ $attempt -gt $max_attempts ]; then
            return 1
        fi
    done
    return 0
}

# Backend 就绪检查
wait_for_backend() {
    local max_attempts=60  # Backend 启动较慢
    local attempt=0
    
    until curl -sf "http://localhost:${BACKEND_PORT}/health" &>/dev/null; do
        sleep 3
        attempt=$((attempt + 1))
        if [ $attempt -gt $max_attempts ]; then
            return 1
        fi
        
        # 每10次检查显示一次进度
        if [ $((attempt % 10)) -eq 0 ]; then
            info "后端服务启动中... (${attempt}/${max_attempts})"
        fi
    done
    return 0
}

# 健康检查
health_check() {
    info "执行健康检查..."
    
    # 检查前端是否可访问
    if curl -sf "http://localhost:${FRONTEND_PORT}" &>/dev/null; then
        ok "前端服务健康"
    else
        warn "前端服务可能未完全就绪"
    fi
    
    # 检查 API 文档
    if curl -sf "http://localhost:${BACKEND_PORT}/docs" &>/dev/null; then
        ok "API 文档可访问"
    else
        warn "API 文档暂时无法访问"
    fi
}

# 显示服务日志（调试用）
show_service_logs() {
    local service=$1
    echo ""
    error "=== $service 服务日志 ==="
    docker compose logs --tail=20 "$service" 2>&1 | tee -a "$LOG_FILE"
    echo ""
}

# ── 结果展示函数 ────────────────────────────────────────

# 显示成功信息
show_success() {
    local elapsed=$(( $(date +%s) - START_TIME ))
    local minutes=$((elapsed / 60))
    local seconds=$((elapsed % 60))
    
    success "NightMend 启动成功！"
    echo ""
    echo -e "${BOLD}🌐 访问地址${NC}"
    echo -e "   前端界面: ${CYAN}http://localhost:${FRONTEND_PORT}${NC}"
    echo -e "   后端API:  ${CYAN}http://localhost:${BACKEND_PORT}${NC}"
    echo -e "   接口文档: ${CYAN}http://localhost:${BACKEND_PORT}/docs${NC}"
    echo ""
    echo -e "${BOLD}🔑 默认账号${NC}"  
    echo -e "   用户名: ${YELLOW}admin${NC}"
    echo -e "   密  码: ${YELLOW}admin123${NC}"
    echo ""
    echo -e "${BOLD}⚡ 下一步${NC}"
    echo "   1. 点击访问前端界面"
    echo "   2. 使用默认账号登录"
    echo "   3. 立即修改默认密码"
    echo "   4. 开始配置监控项"
    echo ""
    echo -e "${BOLD}🛠 管理命令${NC}"
    echo "   查看状态: ${CYAN}docker compose ps${NC}"
    echo "   查看日志: ${CYAN}docker compose logs -f${NC}" 
    echo "   停止服务: ${CYAN}docker compose down${NC}"
    echo "   重启服务: ${CYAN}docker compose restart${NC}"
    echo ""
    if [ -n "$(grep -o '^AI_API_KEY=.*[^[:space:]]' .env 2>/dev/null)" ]; then
        ok "AI 功能已启用，可进行智能运维分析"
    else
        info "如需启用 AI 功能，请编辑 .env 文件中的 AI_API_KEY"
    fi
    echo ""
    echo -e "🕒 总启动时间: ${GREEN}${minutes}分${seconds}秒${NC}"
    echo -e "📋 配置文件: ${PWD}/.env"
    echo -e "📝 启动日志: ${LOG_FILE}"
    echo ""
}

# 显示容器状态
show_status() {
    step "服务状态"
    docker compose ps
    echo ""
}

# ── 主流程 ──────────────────────────────────────────────

main() {
    # 标题
    echo ""
    echo -e "${BLUE}${BOLD}╔═══════════════════════════════════════════╗${NC}"
    echo -e "${BLUE}${BOLD}║           NightMend 快速启动              ║${NC}"
    echo -e "${BLUE}${BOLD}║        开源智能运维监控平台              ║${NC}" 
    echo -e "${BLUE}${BOLD}╚═══════════════════════════════════════════╝${NC}"
    echo ""
    
    log "=== NightMend 快速启动开始 ==="
    log "参数: $*"
    log "工作目录: $PWD"
    
    # 环境检查
    check_docker
    check_ports
    
    if [ "$DRY_RUN" = true ]; then
        ok "环境检查完成（dry-run 模式）"
        exit 0
    fi
    
    # 配置生成
    generate_env
    generate_port_override
    
    # 服务启动
    start_services
    wait_for_services
    
    # 显示结果  
    show_status
    show_success
    
    log "=== NightMend 快速启动完成 ==="
}

# 检查是否在正确的目录
if [ ! -f docker-compose.yml ] && [ ! -f docker-compose.yaml ]; then
    error "未找到 docker-compose.yml 文件"
    echo ""
    echo "请确保在 NightMend 项目根目录下运行此脚本："
    echo "   cd nightmend"
    echo "   bash quickstart.sh"
    echo ""
    exit 1
fi

# 执行主流程
main "$@"