#!/bin/bash
# =============================================================================
# NightMend Agent 安装脚本
# =============================================================================
#
# 用法：
#   cd nightmend
#   sudo ./scripts/install-agent.sh --server URL --token TOKEN
#
# 功能：
#   - 检测并安装 Python 3.9+
#   - 从本地 agent/ 目录安装客户端
#   - 生成配置文件
#   - 安装 systemd 服务
#
set -e

# =============================================================================
# 常量
# =============================================================================
readonly SCRIPT_VERSION="2.0.0"
readonly INSTALL_DIR="/opt/nightmend-agent"
readonly CONFIG_DIR="/etc/nightmend"
readonly CONFIG_FILE="$CONFIG_DIR/agent.yaml"
readonly SERVICE_NAME="nightmend-agent"
readonly VENV_DIR="$INSTALL_DIR/venv"
readonly MIN_PYTHON="3.9"

# =============================================================================
# 颜色
# =============================================================================
readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly CYAN='\033[0;36m'
readonly NC='\033[0m'

msg()  { echo -e "${GREEN}[NightMend]${NC} $*"; }
info() { echo -e "${CYAN}[INFO]${NC}    $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}    $*"; }
err()  { echo -e "${RED}[ERROR]${NC}   $*" >&2; }
die()  { err "$*"; exit 1; }

# =============================================================================
# 参数
# =============================================================================
SERVER_URL=""
AGENT_TOKEN=""
HOST_NAME=""
DISPLAY_NAME=""
METRICS_INTERVAL="15"
UPGRADE=false
UNINSTALL=false
NO_DB=false

show_help() {
    cat <<EOF
NightMend Agent 安装程序 v${SCRIPT_VERSION}

用法:
  sudo ./scripts/install-agent.sh --server URL --token TOKEN [选项]

必需参数:
  --server, -s URL       NightMend 服务端地址 (如: http://192.168.1.100:8001)
  --token, -t TOKEN      Agent Token (从 设置 → Agent Tokens 获取)

可选参数:
  --hostname, -n NAME    主机名 (默认: 自动检测)
  --display-name NAME    显示名称 (默认: 同主机名)
  --interval, -i SEC     采集间隔秒数 (默认: 15)
  --no-db                不安装数据库驱动 (减小依赖)
  --upgrade              升级现有安装
  --uninstall            完全卸载
  --help, -h             显示此帮助

示例:
  # 标准安装
  sudo ./scripts/install-agent.sh --server http://192.168.1.100:8001 --token abc123

  # 指定主机名和采集间隔
  sudo ./scripts/install-agent.sh -s http://192.168.1.100:8001 -t abc123 -n web-server -i 30

  # 升级
  sudo ./scripts/install-agent.sh --upgrade

  # 卸载
  sudo ./scripts/install-agent.sh --uninstall

EOF
    exit 0
}

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --server|-s)      SERVER_URL="$2"; shift 2 ;;
            --token|-t)       AGENT_TOKEN="$2"; shift 2 ;;
            --hostname|-n)    HOST_NAME="$2"; shift 2 ;;
            --display-name)   DISPLAY_NAME="$2"; shift 2 ;;
            --interval|-i)    METRICS_INTERVAL="$2"; shift 2 ;;
            --no-db)          NO_DB=true; shift ;;
            --upgrade)        UPGRADE=true; shift ;;
            --uninstall)      UNINSTALL=true; shift ;;
            --help|-h)        show_help ;;
            *)                die "未知参数: $1 (使用 --help 查看帮助)" ;;
        esac
    done
}

# =============================================================================
# 卸载
# =============================================================================
do_uninstall() {
    msg "正在卸载 NightMend Agent..."

    systemctl stop "$SERVICE_NAME" 2>/dev/null || true
    systemctl disable "$SERVICE_NAME" 2>/dev/null || true
    rm -f "/etc/systemd/system/$SERVICE_NAME.service"
    systemctl daemon-reload 2>/dev/null || true
    rm -rf "$INSTALL_DIR"

    msg "卸载完成"
    msg "配置文件已保留: $CONFIG_DIR"
    msg "如需删除配置: rm -rf $CONFIG_DIR"
    exit 0
}

# =============================================================================
# 系统检测
# =============================================================================
detect_os() {
    if [[ -f /etc/os-release ]]; then
        source /etc/os-release
        OS_ID="${ID}"
        OS_VERSION="${VERSION_ID:-unknown}"
        OS_FAMILY=$(
            case "$ID" in
                centos|rhel|rocky|almalinux|fedora|anolis|opencloudos) echo "rhel" ;;
                ubuntu|debian|linuxmint|kylin)                        echo "debian" ;;
                alpine)                                                  echo "alpine" ;;
                *)                                                       echo "unknown" ;;
            esac
        )
    else
        die "无法检测操作系统"
    fi
    info "系统: ${OS_ID} ${OS_VERSION} (${OS_FAMILY})"
}

# =============================================================================
# Python 检测和安装
# =============================================================================
find_python() {
    local candidates=("python3.12" "python3.11" "python3.10" "python3.9" "python3")

    for cmd in "${candidates[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            local ver
            ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || continue

            # 版本比较
            local major minor req_major req_minor
            IFS='.' read -r major minor <<< "$ver"
            IFS='.' read -r req_major req_minor <<< "$MIN_PYTHON"

            if (( major > req_major )) || (( major == req_major && minor >= req_minor )); then
                echo "$cmd"
                return 0
            fi
        fi
    done
    return 1
}

install_python() {
    info "安装 Python ${MIN_PYTHON}+ ..."

    case "$OS_FAMILY" in
        debian)
            apt-get update -qq
            apt-get install -y -qq python3 python3-venv python3-pip
            ;;
        rhel)
            if command -v dnf &>/dev/null; then
                dnf install -y python3 python3-pip
            else
                yum install -y python3 python3-pip
            fi
            ;;
        alpine)
            apk add --no-cache python3 py3-pip
            ;;
        *)
            die "不支持自动安装 Python，请手动安装 Python ${MIN_PYTHON}+"
            ;;
    esac
}

ensure_python() {
    local python_cmd
    if python_cmd=$(find_python); then
        PYTHON_CMD="$python_cmd"
        info "Python: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1 | cut -d' ' -f2))"
    else
        install_python
        PYTHON_CMD=$(find_python) || die "Python 安装失败"
    fi

    # 确保 venv 模块可用
    if ! $PYTHON_CMD -c "import venv" 2>/dev/null; then
        info "安装 python3-venv ..."
        case "$OS_FAMILY" in
            debian) apt-get install -y -qq python3-venv ;;
            rhel)   dnf install -y python3-virtualenv 2>/dev/null || yum install -y python3-virtualenv 2>/dev/null || true ;;
        esac
    fi
}

# =============================================================================
# 查找 agent 目录
# =============================================================================
find_agent_dir() {
    # 获取脚本所在目录
    local script_dir
    script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

    # 可能的位置
    local candidates=(
        "${script_dir}/../agent"      # scripts/install-agent.sh -> ../agent
        "${script_dir}/agent"         # install-agent.sh 在根目录 -> ./agent
        "./agent"                     # 当前目录下
        "../agent"                    # 上级目录
    )

    for dir in "${candidates[@]}"; do
        local abs_dir
        abs_dir=$(cd "$dir" 2>/dev/null && pwd) || continue
        if [[ -f "${abs_dir}/pyproject.toml" ]] && grep -q "nightmend-agent" "${abs_dir}/pyproject.toml" 2>/dev/null; then
            echo "$abs_dir"
            return 0
        fi
    done

    return 1
}

# =============================================================================
# 安装客户端
# =============================================================================
install_agent() {
    local agent_dir="$1"

    info "安装目录: $INSTALL_DIR"
    info "Agent 源码: $agent_dir"

    mkdir -p "$INSTALL_DIR"

    # 创建虚拟环境
    if [[ ! -d "$VENV_DIR" ]]; then
        info "创建虚拟环境..."
        "$PYTHON_CMD" -m venv "$VENV_DIR"
    fi

    # 升级 pip
    "$VENV_DIR/bin/pip" install -q --upgrade pip

    # 安装 agent
    info "安装 nightmend-agent..."
    local install_opts=()
    if $NO_DB; then
        # 不安装数据库驱动
        "$VENV_DIR/bin/pip" install -q "$agent_dir"
    else
        # 安装全部依赖（包括数据库驱动）
        "$VENV_DIR/bin/pip" install -q "$agent_dir[db]"
    fi

    # 验证安装
    if ! "$VENV_DIR/bin/nightmend-agent" --version &>/dev/null; then
        die "Agent 安装验证失败"
    fi

    msg "安装成功: $($VENV_DIR/bin/nightmend-agent --version 2>&1 || echo "v0.1.0")"
}

# =============================================================================
# 生成配置文件
# =============================================================================
generate_config() {
    if $UPGRADE && [[ -f "$CONFIG_FILE" ]]; then
        msg "保留现有配置: $CONFIG_FILE"
        return
    fi

    info "生成配置文件..."
    mkdir -p "$CONFIG_DIR"

    # 检测主机名
    if [[ -z "$HOST_NAME" ]]; then
        HOST_NAME=$(hostname -f 2>/dev/null || hostname 2>/dev/null || echo "unknown")
    fi

    # 显示名称
    if [[ -z "$DISPLAY_NAME" ]]; then
        DISPLAY_NAME="$HOST_NAME"
    fi

    cat > "$CONFIG_FILE" <<YAML
# NightMend Agent 配置文件
# 生成时间: $(date -u +%Y-%m-%dT%H:%M:%SZ)

server:
  url: "${SERVER_URL}"
  token: "${AGENT_TOKEN}"

host:
  name: "${HOST_NAME}"
  display_name: "${DISPLAY_NAME}"
  tags: []

metrics:
  interval: ${METRICS_INTERVAL}s

# 服务检查 (按需添加)
# services:
#   - name: "nginx"
#     type: process
#     pattern: "nginx"
#   - name: "api"
#     type: http
#     url: "http://localhost:8080/health"

# 日志采集 (按需添加)
# log_sources:
#   - path: /var/log/syslog
#     service: system

# 数据库监控 (按需添加)
# databases:
#   - name: "postgres"
#     type: postgresql
#     host: localhost
#     port: 5432

discovery:
  docker: true
  process: true
YAML

    chmod 600 "$CONFIG_FILE"
    msg "配置文件: $CONFIG_FILE"
}

# =============================================================================
# 安装 systemd 服务
# =============================================================================
install_systemd_service() {
    if ! command -v systemctl &>/dev/null; then
        warn "未检测到 systemd，跳过服务安装"
        return
    fi

    info "安装 systemd 服务..."

    cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=NightMend Monitoring Agent
Documentation=https://github.com/LinChuang2008/nightmend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=${VENV_DIR}/bin/nightmend-agent -c ${CONFIG_FILE} run
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nightmend-agent

# 安全加固
NoNewprivileges=yes
ProtectSystem=strict
ReadWritePaths=${INSTALL_DIR} ${CONFIG_DIR} /tmp

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "$SERVICE_NAME"
    systemctl restart "$SERVICE_NAME"

    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        msg "服务已启动"
    else
        warn "服务启动异常，请检查: journalctl -u $SERVICE_NAME -f"
    fi
}

# =============================================================================
# 输出结果
# =============================================================================
print_result() {
    echo ""
    echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  NightMend Agent 安装成功!${NC}"
    echo -e "${CYAN}══════════════════════════════════════════════════${NC}"
    echo ""
    echo "  安装目录:   $INSTALL_DIR"
    echo "  配置文件:   $CONFIG_FILE"
    echo "  服务端:     $SERVER_URL"
    echo ""
    echo "  常用命令:"
    echo "    查看状态:  systemctl status $SERVICE_NAME"
    echo "    查看日志:  journalctl -u $SERVICE_NAME -f"
    echo "    重启服务:  systemctl restart $SERVICE_NAME"
    echo "    验证配置:  $VENV_DIR/bin/nightmend-agent check"
    echo ""
}

# =============================================================================
# 主流程
# =============================================================================
main() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║    NightMend Agent 安装程序 v${SCRIPT_VERSION}            ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
    echo ""

    # 解析参数
    parse_args "$@"

    # 卸载
    if $UNINSTALL; then
        do_uninstall
    fi

    # 检查 root 权限
    if [[ $EUID -ne 0 ]]; then
        die "请使用 root 或 sudo 运行"
    fi

    # 系统检测
    detect_os

    # 升级模式
    if $UPGRADE; then
        if [[ ! -d "$INSTALL_DIR" ]]; then
            die "未找到现有安装，请先执行全新安装"
        fi
        msg "升级模式: 保留配置"
        SERVER_URL=$(grep -oP '^  url:\s*"\K[^"]+' "$CONFIG_FILE" 2>/dev/null || echo "")
        AGENT_TOKEN=$(grep -oP '^  token:\s*"\K[^"]+' "$CONFIG_FILE" 2>/dev/null || echo "")
    fi

    # 验证参数
    if ! $UPGRADE; then
        [[ -z "$SERVER_URL" ]] && die "缺少 --server 参数"
        [[ -z "$AGENT_TOKEN" ]] && die "缺少 --token 参数"
    fi

    # 查找 agent 目录
    local agent_dir
    if ! agent_dir=$(find_agent_dir); then
        die "未找到 agent 目录，请确保在 nightmend 仓库目录下运行此脚本"
    fi
    info "Agent 目录: $agent_dir"

    # 安装 Python
    ensure_python

    # 安装客户端
    install_agent "$agent_dir"

    # 生成配置
    generate_config

    # 安装服务
    install_systemd_service

    # 输出结果
    print_result
}

main "$@"
