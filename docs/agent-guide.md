# NightMend Agent 使用指南

## 目录

- [概述](#概述)
- [系统要求](#系统要求)
- [安装方式](#安装方式)
  - [方案一：全自动安装脚本](#方案一全自动安装脚本)
  - [方案二：半自动安装（推荐内网环境）](#方案二半自动安装推荐内网环境)
  - [方案三：手动安装](#方案三手动安装)
- [配置文件详解](#配置文件详解)
- [Agent 模块说明](#agent-模块说明)
- [CLI 命令](#cli-命令)
- [systemd 服务管理](#systemd-服务管理)
- [多主机批量部署](#多主机批量部署)
- [升级与卸载](#升级与卸载)
- [故障排查](#故障排查)

---

## 概述

NightMend Agent 是安装在被监控主机上的轻量级 Python 进程，负责：

- **系统指标采集** — CPU、内存、磁盘、网络
- **服务健康检查** — HTTP / TCP 端口探测
- **日志采集** — 文件 tail、多行合并、Docker json-log 解析
- **数据库指标采集** — PostgreSQL / MySQL / Oracle
- **Docker 容器自动发现** — 自动检测运行中的容器并注册为服务
- **宿主机服务发现** — 通过 `ss -tlnp` 自动发现监听端口的服务

Agent 通过 HTTP 将采集的数据上报到 NightMend 后端，由后端统一处理告警、AI 分析和可视化展示。

---

## 系统要求

| 项目 | 要求 |
|------|------|
| 操作系统 | Linux（Ubuntu/Debian/CentOS/RHEL/Rocky/Alma/Fedora） |
| Python | ≥ 3.9 |
| 网络 | 能访问 NightMend 后端（默认端口 8001） |
| 权限 | root（systemd 安装需要） |

---

## 安装方式

### 方案一：全自动安装脚本

脚本会自动检测并安装 Python、创建虚拟环境、生成配置、注册 systemd 服务。

**前提：** 需要在 nightmend 仓库根目录下执行（脚本从本地 `agent/` 目录安装）。

```bash
# 克隆仓库
git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend

# 添加执行权限
chmod +x ./scripts/install-agent.sh

# 一键安装
sudo ./scripts/install-agent.sh \
  --server http://YOUR_SERVER:8001 \
  --token YOUR_TOKEN
```

**内网环境（无法访问 GitHub）** 可从 NightMend 后端直接下载脚本：

```bash
curl -fsSL http://YOUR_SERVER:8001/api/v1/agent/install.sh \
  | bash -s -- --server http://YOUR_SERVER:8001 --token YOUR_TOKEN
```

> 注意：此方式脚本仍需要本地存在 `agent/` 目录，适合已有仓库的场景。

#### 参数说明

| 参数 | 简写 | 必填 | 说明 |
|------|------|------|------|
| `--server` | `-s` | ✅ | NightMend 后端地址，如 `http://192.168.1.100:8001` |
| `--token` | `-t` | ✅ | Agent Token（在「设置 → Agent Tokens」中获取） |
| `--hostname` | `-n` | ❌ | 自定义主机名，默认自动检测 |
| `--display-name` | — | ❌ | 自定义显示名称（在 NightMend 界面中显示） |
| `--interval` | `-i` | ❌ | 指标采集间隔（秒），默认 15 |
| `--no-db` | — | ❌ | 不安装数据库驱动，减小依赖体积 |
| `--upgrade` | — | ❌ | 升级已有安装，保留配置文件 |
| `--uninstall` | — | ❌ | 完全卸载 Agent |

#### 安装后目录结构

```
/opt/nightmend-agent/
└── venv/
    └── bin/nightmend-agent    # Agent 可执行文件

/etc/nightmend/
└── agent.yaml                # 配置文件

/etc/systemd/system/
└── nightmend-agent.service    # systemd 服务文件
```

---

### 方案二：半自动安装（推荐内网环境）

适用于无法访问外网、或自动安装 Python 失败的场景。先手动安装 Python 3.9+，再执行安装脚本。

#### 第一步：安装 Python 3.9+

根据你的发行版选择对应命令：

**Ubuntu 20.04 / 22.04 / 24.04**

```bash
# 换源（阿里云，可选）
sudo sed -i 's|http://archive.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list
sudo sed -i 's|http://security.ubuntu.com|http://mirrors.aliyun.com|g' /etc/apt/sources.list

# 安装 Python 3.9+（Ubuntu 20.04 默认是 3.8，需要 deadsnakes PPA）
sudo apt-get update
sudo apt-get install -y software-properties-common
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt-get update
sudo apt-get install -y python3.9 python3.9-venv python3.9-distutils

# Ubuntu 22.04+ 自带 Python 3.10，直接安装即可
# sudo apt-get install -y python3 python3-venv python3-pip
```

**Debian 11 (Bullseye) / 12 (Bookworm)**

```bash
# 换源（清华源，可选）
sudo tee /etc/apt/sources.list > /dev/null <<'EOF'
# Debian 12 Bookworm
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm main contrib non-free non-free-firmware
deb https://mirrors.tuna.tsinghua.edu.cn/debian/ bookworm-updates main contrib non-free non-free-firmware
deb https://mirrors.tuna.tsinghua.edu.cn/debian-security bookworm-security main contrib non-free non-free-firmware
EOF
# Debian 11 将上面 bookworm 替换为 bullseye

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip
```

**CentOS 7**

```bash
# 换源（阿里云，可选）
sudo mv /etc/yum.repos.d/CentOS-Base.repo /etc/yum.repos.d/CentOS-Base.repo.bak
sudo curl -o /etc/yum.repos.d/CentOS-Base.repo \
  http://mirrors.aliyun.com/repo/Centos-7.repo
sudo yum makecache

# CentOS 7 默认 Python 3.6，需要通过 SCL 或 IUS 安装 3.9
sudo yum install -y centos-release-scl
sudo yum install -y rh-python39 rh-python39-python-pip

# 激活（临时）
scl enable rh-python39 bash

# 或者创建软链接（永久）
sudo ln -sf /opt/rh/rh-python39/root/usr/bin/python3.9 /usr/local/bin/python3.9
```

**CentOS 8 / Rocky Linux 8 / AlmaLinux 8**

```bash
# 换源（阿里云，可选）
sudo sed -i 's|mirrorlist=|#mirrorlist=|g' /etc/yum.repos.d/CentOS-*.repo
sudo sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://mirrors.aliyun.com|g' /etc/yum.repos.d/CentOS-*.repo
# Rocky/Alma 换源
sudo sed -i 's|https://dl.rockylinux.org|https://mirrors.aliyun.com/rockylinux|g' /etc/yum.repos.d/*.repo

sudo dnf install -y python39 python39-pip
# 设为默认（可选）
sudo alternatives --set python3 /usr/bin/python3.9
```

**CentOS 9 / Rocky Linux 9 / AlmaLinux 9**

```bash
sudo dnf install -y python3 python3-pip
# 默认即为 Python 3.9+，无需额外操作
```

**pip 换源（所有发行版通用）**

```bash
# 换为阿里云 PyPI 镜像
pip3 config set global.index-url https://mirrors.aliyun.com/pypi/simple/
pip3 config set global.trusted-host mirrors.aliyun.com

# 或清华源
pip3 config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/
pip3 config set global.trusted-host pypi.tuna.tsinghua.edu.cn
```

#### 第二步：执行安装脚本

Python 安装完成后，执行安装脚本（脚本会自动检测到已有的 Python 3.9+，跳过安装步骤）：

```bash
# 确保在 nightmend 仓库根目录
cd /path/to/nightmend

chmod +x ./scripts/install-agent.sh
sudo ./scripts/install-agent.sh \
  --server http://YOUR_SERVER:8001 \
  --token YOUR_TOKEN \
  --display-name "我的服务器"
```

验证安装：

```bash
systemctl status nightmend-agent
journalctl -u nightmend-agent -f
```

---

### 方案三：手动安装

适用于需要完全控制安装过程、或不使用 systemd 的场景。

#### 第一步：获取代码

```bash
git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend/agent
```

或直接将 `agent/` 目录复制到目标机器：

```bash
# 在有仓库的机器上打包
tar czf nightmend-agent.tar.gz -C /path/to/nightmend agent/

# 传输到目标机器
scp nightmend-agent.tar.gz root@TARGET_HOST:/opt/

# 在目标机器上解压
cd /opt && tar xzf nightmend-agent.tar.gz
cd agent
```

#### 第二步：创建虚拟环境并安装

```bash
# 创建安装目录
sudo mkdir -p /opt/nightmend-agent

# 创建虚拟环境（指定 Python 版本）
python3.9 -m venv /opt/nightmend-agent/venv
# 或使用系统默认 python3
python3 -m venv /opt/nightmend-agent/venv

# 激活虚拟环境
source /opt/nightmend-agent/venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装 Agent（含数据库监控驱动）
pip install ".[db]"

# 不需要数据库监控时
# pip install .

# 验证安装
nightmend-agent --version
```

#### 第三步：生成配置文件

```bash
sudo mkdir -p /etc/nightmend

sudo tee /etc/nightmend/agent.yaml > /dev/null <<EOF
server:
  url: http://YOUR_SERVER:8001
  token: YOUR_TOKEN

host:
  name: $(hostname -f 2>/dev/null || hostname)
  display_name: "自定义显示名称"
  tags: []

metrics:
  interval: 15s

discovery:
  docker: true
  process: true
EOF

# 限制配置文件权限（含 Token，不应对外可读）
sudo chmod 600 /etc/nightmend/agent.yaml
```

#### 第四步：验证配置

```bash
/opt/nightmend-agent/venv/bin/nightmend-agent -c /etc/nightmend/agent.yaml check
```

正常输出示例：

```
[OK] 配置文件加载成功
[OK] 服务端连接正常: http://YOUR_SERVER:8001
[OK] Token 验证通过
[OK] 主机名: my-server-01
```

#### 第五步：前台测试运行

```bash
/opt/nightmend-agent/venv/bin/nightmend-agent -v -c /etc/nightmend/agent.yaml run
```

确认日志中出现 `HTTP 201 Created` 表示数据上报成功，`Ctrl+C` 停止。

#### 第六步：注册 systemd 服务

```bash
sudo tee /etc/systemd/system/nightmend-agent.service > /dev/null <<EOF
[Unit]
Description=NightMend Monitoring Agent
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
ExecStart=/opt/nightmend-agent/venv/bin/nightmend-agent -c /etc/nightmend/agent.yaml run
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=nightmend-agent
NoNewPrivileges=yes
ProtectSystem=strict
ReadWritePaths=/opt/nightmend-agent /etc/nightmend /tmp

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable nightmend-agent
sudo systemctl start nightmend-agent

# 确认运行状态
sudo systemctl status nightmend-agent
```

---

## 配置文件详解

配置文件为 YAML 格式，默认路径 `/etc/nightmend/agent.yaml`。时间间隔支持简写：`15s`（秒）、`1m`（分钟），也可直接写整数（按秒计算）。

### server - 服务端连接

```yaml
server:
  url: http://192.168.1.100:8001   # NightMend 后端地址（必填）
  token: "your-agent-token"        # Agent Token（必填）
```

### host - 主机标识

```yaml
host:
  name: "web-server-01"            # 主机名（可选，默认自动检测）
  display_name: "生产-Web-01"      # 界面显示名称（优先于 name 显示）
  tags: ["production", "web"]      # 标签，用于分组筛选（可选）
```

### metrics - 指标采集

```yaml
metrics:
  interval: 15s                    # 采集间隔（可选，默认 15s）
```

### services - 服务健康检查

```yaml
services:
  # HTTP 检查
  - name: "My API"
    type: http
    url: http://localhost:8080/health
    interval: 30s
    timeout: 10

  # TCP 端口检查
  - name: "Redis"
    type: tcp
    host: localhost
    port: 6379
    interval: 30s
```

### log_sources - 日志采集

```yaml
log_sources:
  - path: /var/log/syslog
    service: system
    multiline: false

  - path: /var/log/nginx/error.log
    service: nginx

  - path: /var/lib/docker/containers/abc123/abc123-json.log
    service: my-app
    docker: true                   # Docker JSON 日志格式
```

### discovery - 自动发现

```yaml
discovery:
  docker: true                     # 自动发现 Docker 容器
  process: true                    # 自动发现宿主机监听服务
  interval: 30                     # 发现的服务默认检查间隔
```

### databases - 数据库监控

```yaml
databases:
  - name: "主库"
    type: postgres                 # postgres / mysql / oracle
    host: localhost
    port: 5432
    database: mydb
    username: monitor
    password: "monitor_pass"
    interval: 60s

  - name: "业务数据库"
    type: mysql
    host: 10.0.0.10
    port: 3306
    database: app_db
    username: monitor
    password: "pass"
```

### 完整配置示例

```yaml
server:
  url: http://192.168.1.100:8001
  token: "abc123-your-token"

host:
  name: "prod-web-01"
  display_name: "生产-Web-01"
  tags: ["production", "web"]

metrics:
  interval: 15s

services:
  - name: "Nginx"
    type: http
    url: http://localhost/health
    interval: 30s
  - name: "Redis"
    type: tcp
    host: localhost
    port: 6379

log_sources:
  - path: /var/log/nginx/error.log
    service: nginx
  - path: /var/log/app/app.log
    service: app
    multiline: true

discovery:
  docker: true
  process: true

databases:
  - name: "PostgreSQL 主库"
    type: postgres
    host: localhost
    port: 5432
    database: app_db
    username: monitor
    password: "monitor123"
    interval: 60s
```

---

## Agent 模块说明

| 模块 | 文件 | 功能 |
|------|------|------|
| 系统指标采集 | `collector.py` | 采集 CPU、内存、磁盘、网络 |
| 服务健康检查 | `checker.py` | HTTP / TCP 健康检查，记录响应时间 |
| 日志采集 | `log_collector.py` | Tail 日志，支持多行合并和 Docker json-log |
| 数据库指标 | `db_collector.py` | 采集 PostgreSQL / MySQL / Oracle 指标 |
| 自动发现 | `discovery.py` | 自动发现 Docker 容器和宿主机监听服务 |
| 数据上报 | `reporter.py` | 汇总数据，HTTP POST 上报到后端，处理自动更新 |
| 命令行入口 | `cli.py` | 提供 `run`、`check`、`configure` 等 CLI 命令 |
| 配置加载 | `config.py` | 解析 YAML 配置，支持环境变量覆盖 |

---

## CLI 命令

```bash
# 查看版本
nightmend-agent --version

# 交互式配置向导（首次使用）
nightmend-agent configure

# 验证配置文件
nightmend-agent -c /etc/nightmend/agent.yaml check

# 前台运行（调试用）
nightmend-agent -c /etc/nightmend/agent.yaml run

# 详细日志模式
nightmend-agent -v -c /etc/nightmend/agent.yaml run
```

---

## systemd 服务管理

```bash
# 启用并启动
systemctl daemon-reload
systemctl enable nightmend-agent
systemctl start nightmend-agent

# 查看状态
systemctl status nightmend-agent

# 查看日志
journalctl -u nightmend-agent -f              # 实时日志
journalctl -u nightmend-agent --since today   # 今日日志

# 重启 / 停止
systemctl restart nightmend-agent
systemctl stop nightmend-agent
```

---

## 多主机批量部署

### SSH 批量执行

```bash
#!/bin/bash
SERVER_URL="http://192.168.1.100:8001"
TOKEN="your-agent-token"

while IFS= read -r host; do
  echo "=== Installing on $host ==="
  scp -r /path/to/nightmend root@"$host":/opt/nightmend
  ssh root@"$host" "cd /opt/nightmend && \
    sudo ./scripts/install-agent.sh --server $SERVER_URL --token $TOKEN"
done < hosts.txt
```

### Ansible Playbook

```yaml
---
- name: Deploy NightMend Agent
  hosts: monitored_servers
  become: yes
  vars:
    nightmend_server: "http://192.168.1.100:8001"
    nightmend_token: "your-agent-token"
  tasks:
    - name: Copy nightmend repo
      synchronize:
        src: /path/to/nightmend/
        dest: /opt/nightmend/
    - name: Install NightMend Agent
      shell: |
        cd /opt/nightmend && \
        ./scripts/install-agent.sh \
          --server {{ nightmend_server }} \
          --token {{ nightmend_token }}
      args:
        creates: /opt/nightmend-agent/venv/bin/nightmend-agent
```

---

## 升级与卸载

### 升级

```bash
# 拉取最新代码后执行升级（保留现有配置）
cd /path/to/nightmend
git pull
chmod +x ./scripts/install-agent.sh
sudo ./scripts/install-agent.sh --upgrade
```

### 卸载

```bash
# 卸载 Agent（保留配置文件）
chmod +x ./scripts/install-agent.sh
sudo ./scripts/install-agent.sh --uninstall

# 同时删除配置
sudo rm -rf /etc/nightmend
```

---

## 故障排查

### Agent 无法启动

```bash
# 1. 检查服务状态
systemctl status nightmend-agent

# 2. 查看详细日志
journalctl -u nightmend-agent -n 50 --no-pager

# 3. 验证配置文件
/opt/nightmend-agent/venv/bin/nightmend-agent -c /etc/nightmend/agent.yaml check

# 4. 前台模式运行，查看实时输出
/opt/nightmend-agent/venv/bin/nightmend-agent -v -c /etc/nightmend/agent.yaml run
```

### Agent 运行但数据不上报

```bash
# 1. 确认网络连通性
curl -s http://YOUR_SERVER:8001/api/health

# 2. 检查 Token 是否正确（在 NightMend 后台确认 Token 状态）

# 3. 查看 Agent 日志中的错误
journalctl -u nightmend-agent --since "10 minutes ago" | grep -i error
```

### 常见错误及解决

| 错误 | 原因 | 解决方案 |
|------|------|----------|
| `No agent token configured` | 未配置 Token | 在 `agent.yaml` 中设置 `server.token` |
| `Config file not found` | 配置文件路径错误 | 确认 `/etc/nightmend/agent.yaml` 存在，或用 `-c` 指定路径 |
| `Connection refused` | 后端不可达 | 检查 `server.url` 地址和端口，确认防火墙规则 |
| `401 Unauthorized` | Token 无效或过期 | 在 NightMend 后台重新生成 Token |
| `Permission denied` 读日志 | Agent 无权读取日志文件 | 确保 Agent 以 root 运行 |
| `ModuleNotFoundError` | 虚拟环境未激活或安装不完整 | 重新执行 `pip install ".[db]"` |
| Python 版本过低 | 系统 Python < 3.9 | 参考[方案二](#方案二半自动安装推荐内网环境)手动安装 Python 3.9+ |
