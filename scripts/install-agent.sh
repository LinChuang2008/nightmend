#!/usr/bin/env bash
# VigilOps Agent One-Click Installer / Agent 一键安装脚本
# Usage: curl -fsSL https://raw.githubusercontent.com/LinChuang2008/vigilops/main/scripts/install-agent.sh | bash -s -- --server URL --token TOKEN
#
# Or download and run:
#   chmod +x install-agent.sh
#   ./install-agent.sh --server http://your-vigilops:3001 --token your-token
set -euo pipefail

# ── Constants ──────────────────────────────────────────────
AGENT_VERSION="0.1.0"
INSTALL_DIR="/opt/vigilops-agent"
CONFIG_DIR="/etc/vigilops"
CONFIG_FILE="$CONFIG_DIR/agent.yaml"
SERVICE_NAME="vigilops-agent"
VENV_DIR="$INSTALL_DIR/venv"
REPO_URL="https://github.com/LinChuang2008/vigilops.git"
GITEE_REPO_URL="https://gitee.com/LinChuang2008/vigilops.git"
MIN_PYTHON="3.9"

# ── Colors ─────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

msg()  { echo -e "${GREEN}[VigilOps Agent]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERROR]${NC} $1" >&2; exit 1; }

# ── Parse Arguments ────────────────────────────────────────
SERVER_URL=""
AGENT_TOKEN=""
HOST_NAME=""
METRICS_INTERVAL="15"
UPGRADE=false
UNINSTALL=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --server|-s)    SERVER_URL="$2"; shift 2 ;;
    --token|-t)     AGENT_TOKEN="$2"; shift 2 ;;
    --hostname|-n)  HOST_NAME="$2"; shift 2 ;;
    --interval|-i)  METRICS_INTERVAL="$2"; shift 2 ;;
    --upgrade)      UPGRADE=true; shift ;;
    --uninstall)    UNINSTALL=true; shift ;;
    --local|-l)     LOCAL_PKG="$2"; shift 2 ;;
    --help|-h)
      echo "VigilOps Agent Installer v$AGENT_VERSION"
      echo ""
      echo "Usage: $0 --server URL --token TOKEN [OPTIONS]"
      echo ""
      echo "Required:"
      echo "  --server, -s URL     VigilOps server URL (e.g. http://192.168.1.100:3001)"
      echo "  --token, -t TOKEN    Agent token (from Settings → Agent Tokens)"
      echo ""
      echo "Optional:"
      echo "  --hostname, -n NAME  Override hostname (default: auto-detect)"
      echo "  --interval, -i SEC   Metrics collection interval (default: 15)"
      echo "  --local, -l PATH     Use local agent package (dir or .tar.gz)"
      echo "  --upgrade            Upgrade existing installation"
      echo "  --uninstall          Remove VigilOps Agent completely"
      echo "  --help, -h           Show this help"
      exit 0
      ;;
    *) err "Unknown option: $1. Use --help for usage." ;;
  esac
done

# ── Uninstall ──────────────────────────────────────────────
if $UNINSTALL; then
  msg "Uninstalling VigilOps Agent..."
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  rm -f "/etc/systemd/system/$SERVICE_NAME.service"
  systemctl daemon-reload 2>/dev/null || true
  rm -rf "$INSTALL_DIR"
  msg "Agent removed. Config preserved at $CONFIG_DIR"
  msg "To remove config too: rm -rf $CONFIG_DIR"
  exit 0
fi

# ── Validate ───────────────────────────────────────────────
if ! $UPGRADE; then
  [[ -z "$SERVER_URL" ]] && err "Missing --server. Use --help for usage."
  [[ -z "$AGENT_TOKEN" ]] && err "Missing --token. Use --help for usage."
fi

# ── Check root ─────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  err "Please run as root (sudo) for systemd installation."
fi

# ── Detect OS ──────────────────────────────────────────────
detect_os() {
  if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    echo "$ID"
  elif [[ -f /etc/redhat-release ]]; then
    echo "centos"
  else
    echo "unknown"
  fi
}

OS=$(detect_os)
msg "Detected OS: $OS"

# ── Check / Install Python ─────────────────────────────────
find_python() {
  for cmd in python3.12 python3.11 python3.10 python3.9 python3; do
    if command -v "$cmd" &>/dev/null; then
      local ver
      ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
      if python3 -c "
import sys
cur = tuple(map(int, '$ver'.split('.')))
req = tuple(map(int, '$MIN_PYTHON'.split('.')))
sys.exit(0 if cur >= req else 1)
" 2>/dev/null; then
        echo "$cmd"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON_CMD=""
if PYTHON_CMD=$(find_python); then
  msg "Found Python: $PYTHON_CMD ($($PYTHON_CMD --version 2>&1))"
else
  msg "Python >= $MIN_PYTHON not found. Installing..."
  case "$OS" in
    ubuntu|debian)
      apt-get update -qq && apt-get install -y -qq python3 python3-venv python3-pip
      # Ubuntu 可能需要版本特定的 venv 包（如 python3.10-venv）
      PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "")
      [[ -n "$PYTHON_VER" ]] && apt-get install -y -qq "python${PYTHON_VER}-venv" 2>/dev/null || true
      ;;
    centos|rhel|rocky|alma|fedora)
      dnf install -y python3 python3-pip || yum install -y python3 python3-pip ;;
    *)
      err "Cannot auto-install Python on $OS. Please install Python >= $MIN_PYTHON manually." ;;
  esac
  PYTHON_CMD=$(find_python) || err "Python installation failed."
fi

# ── Install git if needed ──────────────────────────────────
if ! command -v git &>/dev/null; then
  msg "Installing git..."
  case "$OS" in
    ubuntu|debian) apt-get install -y -qq git ;;
    centos|rhel|rocky|alma|fedora) dnf install -y git || yum install -y git ;;
    *) err "Please install git manually." ;;
  esac
fi

# ── Download / Update Agent Code ───────────────────────────
LOCAL_PKG="${LOCAL_PKG:-}"

if [[ -n "$LOCAL_PKG" ]]; then
  # Local package mode: skip git, use provided path
  msg "Using local agent package: $LOCAL_PKG"
  mkdir -p "$INSTALL_DIR/repo"
  if [[ -d "$LOCAL_PKG" ]]; then
    cp -r "$LOCAL_PKG" "$INSTALL_DIR/repo/agent"
  elif [[ -f "$LOCAL_PKG" ]]; then
    tar xzf "$LOCAL_PKG" -C "$INSTALL_DIR/repo/"
  else
    err "Local package not found: $LOCAL_PKG"
  fi
elif [[ -d "$INSTALL_DIR/repo" ]]; then
  msg "Updating agent code..."
  cd "$INSTALL_DIR/repo"
  git pull --ff-only 2>/dev/null || {
    warn "Git pull failed, re-cloning..."
    rm -rf "$INSTALL_DIR/repo"
    git clone --depth 1 "$REPO_URL" "$INSTALL_DIR/repo"
  }
else
  msg "Downloading VigilOps agent..."
  mkdir -p "$INSTALL_DIR"
  # Try GitHub first, fallback to Gitee mirror (faster in China)
  if timeout 30 git clone --depth 1 "$REPO_URL" "$INSTALL_DIR/repo" 2>/dev/null; then
    msg "Cloned from GitHub."
  elif timeout 30 git clone --depth 1 "$GITEE_REPO_URL" "$INSTALL_DIR/repo" 2>/dev/null; then
    msg "Cloned from Gitee mirror."
  else
    err "Failed to clone from GitHub and Gitee. Use --local to provide a local package."
  fi
fi

# ── Setup Virtual Environment ──────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
  msg "Creating virtual environment..."
  "$PYTHON_CMD" -m venv "$VENV_DIR"
fi

msg "Installing agent package..."
"$VENV_DIR/bin/pip" install -q --upgrade pip
"$VENV_DIR/bin/pip" install -q "$INSTALL_DIR/repo/agent[db]"

# Verify
"$VENV_DIR/bin/vigilops-agent" --version
msg "Agent binary installed successfully."

# ── Generate Config ────────────────────────────────────────
if $UPGRADE && [[ -f "$CONFIG_FILE" ]]; then
  msg "Keeping existing config: $CONFIG_FILE"
else
  mkdir -p "$CONFIG_DIR"

  [[ -z "$HOST_NAME" ]] && HOST_NAME=$(hostname -f 2>/dev/null || hostname)

  cat > "$CONFIG_FILE" <<YAML
# VigilOps Agent Configuration
# Generated by install-agent.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)

server:
  url: "$SERVER_URL"
  token: "$AGENT_TOKEN"

host:
  name: "$HOST_NAME"
  tags: []

metrics:
  interval: ${METRICS_INTERVAL}s

# Service checks (add your services here)
# services:
#   - name: "My Web App"
#     type: http
#     url: http://localhost:8080/health
#     interval: 30s

# Log sources (add log files to monitor)
# log_sources:
#   - path: /var/log/syslog
#     service: system
#   - path: /var/log/nginx/error.log
#     service: nginx

# Auto-discovery
discovery:
  docker: true
  process: true
YAML

  msg "Config written: $CONFIG_FILE"
fi

# ── Install Systemd Service ───────────────────────────────
cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=VigilOps Monitoring Agent
Documentation=https://github.com/LinChuang2008/vigilops
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=$VENV_DIR/bin/vigilops-agent -c $CONFIG_FILE run
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=vigilops-agent

# Security hardening
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=$INSTALL_DIR $CONFIG_DIR /tmp

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

# ── Verify ─────────────────────────────────────────────────
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  msg "✅ Agent installed and running!"
else
  warn "Agent service started but may not be healthy yet."
  warn "Check logs: journalctl -u $SERVICE_NAME -f"
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo -e "${GREEN} VigilOps Agent installed successfully!${NC}"
echo -e "${CYAN}════════════════════════════════════════════════${NC}"
echo ""
echo "  Config:  $CONFIG_FILE"
echo "  Service: systemctl status $SERVICE_NAME"
echo "  Logs:    journalctl -u $SERVICE_NAME -f"
echo ""
echo "  Commands:"
echo "    systemctl start/stop/restart $SERVICE_NAME"
echo "    $VENV_DIR/bin/vigilops-agent check   # Validate config"
echo ""
echo "  Upgrade:    $0 --upgrade"
echo "  Uninstall:  $0 --uninstall"
echo ""
