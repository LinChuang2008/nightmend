#!/bin/bash
################################################################################
# VigilOps Agent - CentOS 7 自动安装脚本
#
# 功能：
#   - 备份现有 yum 源配置
#   - 临时安装 Python 3.9 源
#   - 使用本地 agent 目录安装
#   - 恢复原 yum 源配置
#
# 用法：
#   cd /path/to/agent
#   sudo bash install-agent-centos7.sh <SERVER_URL> <AGENT_TOKEN>
#
# 示例：
#   sudo bash install-agent-centos7.sh "http://192.168.1.100:8000" "your-token-here"
################################################################################

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查 root 权限
if [ "$EUID" -ne 0 ]; then
    log_error "请使用 root 权限运行此脚本"
    exit 1
fi

# 参数检查
if [ -z "$1" ] || [ -z "$2" ]; then
    log_error "用法: $0 <SERVER_URL> <AGENT_TOKEN>"
    echo "示例: sudo bash $0 \"http://192.168.1.100:8000\" \"your-token-here\""
    exit 1
fi

SERVER_URL="$1"
AGENT_TOKEN="$2"

log_info "=========================================="
log_info "VigilOps Agent CentOS 7 安装脚本"
log_info "=========================================="
log_info "服务器: $SERVER_URL"
echo ""

# 检查 agent 目录（脚本放在 agent 目录下执行）
AGENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$AGENT_DIR/pyproject.toml" ]; then
    log_error "未找到 pyproject.toml，请确保脚本在 agent 目录下"
    log_error "当前路径: $AGENT_DIR"
    exit 1
fi

log_info "Agent 目录: $AGENT_DIR"

# 定义恢复函数（需要在前面定义，因为后面可能调用）
restore_yum() {
    rm -f /etc/yum.repos.d/*.repo
    cp -r "$YUM_BACKUP_DIR"/* /etc/yum.repos.d/
    log_info "yum 源已恢复"
}

################################################################################
# 步骤 1: 备份 yum 源
################################################################################

log_info "步骤 1: 备份现有 yum 源"

YUM_BACKUP_DIR="/etc/yum.repos.d.bak.vigilops-$(date +%Y%m%d%H%M%S)"
cp -r /etc/yum.repos.d "$YUM_BACKUP_DIR"
log_info "已备份到: $YUM_BACKUP_DIR"

echo ""

################################################################################
# 步骤 2: 配置 Python 3.9 源
################################################################################

log_info "步骤 2: 配置清华源（用于安装编译依赖）"

rm -f /etc/yum.repos.d/*.repo

# 清华大学 CentOS 7 基础源
cat > /etc/yum.repos.d/centos-base.repo << 'EOF'
[base]
name=CentOS-7 - Base - Tsinghua
baseurl=https://mirrors.tuna.tsinghua.edu.cn/centos-vault/7.9.2009/os/x86_64/
enabled=1
gpgcheck=0

[updates]
name=CentOS-7 - Updates - Tsinghua
baseurl=https://mirrors.tuna.tsinghua.edu.cn/centos-vault/7.9.2009/updates/x86_64/
enabled=1
gpgcheck=0

[extras]
name=CentOS-7 - Extras - Tsinghua
baseurl=https://mirrors.tuna.tsinghua.edu.cn/centos-vault/7.9.2009/extras/x86_64/
enabled=1
gpgcheck=0
EOF

# 清华 EPEL 源
cat > /etc/yum.repos.d/epel.repo << 'EOF'
[epel]
name=EPEL 7 - Tsinghua
baseurl=https://mirrors.tuna.tsinghua.edu.cn/epel/7/x86_64/
enabled=1
gpgcheck=0
EOF

log_info "清华源配置完成"

echo ""

################################################################################
# 步骤 3: 安装 Python 3.9
################################################################################

log_info "步骤 3: 编译安装 Python 3.9"

yum clean all -q > /dev/null 2>&1 || true

# 安装编译依赖
log_info "安装编译依赖..."
yum install -y -q gcc make openssl-devel bzip2-devel libffi-devel zlib-devel wget > /dev/null 2>&1 || {
    log_error "编译依赖安装失败"
    restore_yum
    exit 1
}

PYTHON_VERSION="3.9.20"
PYTHON_SRC_DIR="/tmp/Python-$PYTHON_VERSION"

log_info "下载 Python $PYTHON_VERSION 源码（使用清华镜像）..."
wget -q -O "/tmp/Python-$PYTHON_VERSION.tgz" \
    "https://mirrors.tuna.tsinghua.edu.cn/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz" || {
    log_warn "清华镜像下载失败，尝试官方源..."
    curl -sL "https://www.python.org/ftp/python/$PYTHON_VERSION/Python-$PYTHON_VERSION.tgz" -o "/tmp/Python-$PYTHON_VERSION.tgz" || {
        log_error "Python 源码下载失败"
        restore_yum
        exit 1
    }
}

log_info "解压并编译（需要几分钟，请耐心等待）..."
mkdir -p "$PYTHON_SRC_DIR"
tar -xzf "/tmp/Python-$PYTHON_VERSION.tgz" -C /tmp/
cd "$PYTHON_SRC_DIR"

# 配置编译选项
./configure \
    --enable-optimizations \
    --enable-shared \
    --with-ssl \
    --with-lto \
    LDFLAGS="-Wl,-rpath /usr/local/lib" \
    > /dev/null 2>&1

# 编译（使用所有 CPU 核心）
log_info "编译中..."
make -j$(nproc) > /dev/null 2>&1

# 安装
log_info "安装中..."
make altinstall > /dev/null 2>&1

# 配置动态库路径
echo "/usr/local/lib" > /etc/ld.so.conf.d/python3.9.conf
ldconfig > /dev/null 2>&1

PYTHON_CMD="python3.9"
cd /
rm -rf "$PYTHON_SRC_DIR" "/tmp/Python-$PYTHON_VERSION.tgz"

$PYTHON_CMD --version || {
    log_error "Python 3.9 安装失败"
    restore_yum
    exit 1
}

log_info "Python 3.9 安装成功"

echo ""

################################################################################
# 步骤 4: 安装 Agent
################################################################################

log_info "步骤 4: 安装 Agent"

AGENT_INSTALL_DIR="/opt/vigilops"
VENV_DIR="$AGENT_INSTALL_DIR/venv"

mkdir -p "$AGENT_INSTALL_DIR"
$PYTHON_CMD -m venv "$VENV_DIR"

source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q

# 安装编译依赖
yum install -y -q gcc make postgresql-devel openssl-devel > /dev/null 2>&1 || true

# 从本地目录安装
log_info "从本地安装: $AGENT_DIR"
pip install -e "$AGENT_DIR"

deactivate

echo ""

################################################################################
# 步骤 5: 配置
################################################################################

log_info "步骤 5: 配置 Agent"

CONFIG_FILE="/etc/vigilops/agent.yaml"
mkdir -p /etc/vigilops

cat > "$CONFIG_FILE" << EOF
server:
  url: $SERVER_URL
  token: "$AGENT_TOKEN"

host:
  name: ""
  display_name: "$(hostname)"
  tags:
    - centos7

collector:
  interval: 30
EOF

chmod 600 "$CONFIG_FILE"

echo ""

################################################################################
# 步骤 6: 创建服务
################################################################################

log_info "步骤 6: 创建 systemd 服务"

if ! id -u vigilops > /dev/null 2>&1; then
    useradd -r -s /sbin/nologin -d /var/lib/vigilops vigilops
fi

cat > /etc/systemd/system/vigilops-agent.service << EOF
[Unit]
Description=VigilOps Monitoring Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=vigilops
WorkingDirectory=$AGENT_INSTALL_DIR
Environment="PATH=$VENV_DIR/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=$VENV_DIR/bin/vigilops-agent run --config $CONFIG_FILE
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

echo ""

################################################################################
# 步骤 7: 恢复 yum 源
################################################################################

log_info "步骤 7: 恢复 yum 源"

restore_yum

################################################################################
# 步骤 8: 启动服务
################################################################################

log_info "步骤 8: 启动服务"

systemctl daemon-reload
systemctl start vigilops-agent
systemctl enable vigilops-agent > /dev/null 2>&1

sleep 2

if systemctl is-active --quiet vigilops-agent; then
    log_info "✓ 服务启动成功"
else
    log_error "✗ 服务启动失败，查看日志: journalctl -u vigilops-agent -n 50"
fi

echo ""
log_info "=========================================="
log_info "安装完成！"
log_info "=========================================="
echo ""
echo "配置文件: $CONFIG_FILE"
echo "命令:"
echo "  状态: systemctl status vigilops-agent"
echo "  日志: journalctl -u vigilops-agent -f"
echo ""
echo "yum 备份: $YUM_BACKUP_DIR"
