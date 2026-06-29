# NightMend Agent 安装手册

> 版本 v1.1 · 更新 2026-04-22
> 覆盖：Linux (Ubuntu/Debian/CentOS/RHEL) · Windows · macOS · 容器 K8s · 故障排查

---

## 一、Agent 定位

- 在被监控主机运行的**常驻后台进程**，采集：
  - 主机指标（CPU / MEM / DISK / NET）· 10s 粒度
  - 服务探测（HTTP / TCP / systemd）
  - 日志 tail（`journald` / 文件路径）
  - 数据库监控（PG / MySQL / Redis 连接探活 + 指标）
  - GPU 指标（如装 `nvidia-smi`）
- 通过 HTTP(S) 长连接上报到 NightMend 后端
- 支持自动升级（由后端 push wheel 包）

---

## 二、系统要求

| 项 | 要求 |
| --- | --- |
| CPU | 1 核（采集 < 1% 占用） |
| 内存 | 64 MB |
| 磁盘 | 100 MB（agent + 本地缓冲） |
| 网络 | 可访问后端 `:8000/api/v1/agents/*` |
| OS | Linux 3.10+ · Windows 10+ · macOS 11+ |
| Python | 3.9+（如从源码装；wheel 安装自带） |

---

## 三、Linux 安装

### 3.1 快速脚本（Ubuntu / Debian / Rocky / AlmaLinux / RHEL 8+）

> 目前未托管公网 installer，需要先把仓库拉到目标机或从已部署的 NightMend 服务器 `rsync` agent 目录过来。

```bash
# 1. 把 agent 目录拿到目标机（任选一种）
scp -r <nightmend-server>:/opt/nightmend/agent /tmp/nightmend-agent
# 或
git clone --depth 1 https://gitlab.lchuangnet.com/lchuangnet/nightmend.git /tmp/nightmend && \
  cp -r /tmp/nightmend/agent /tmp/nightmend-agent

# 2. 运行安装脚本（脚本内部会按系统版本选择对应流程）
cd /tmp/nightmend-agent
sudo bash scripts/install-agent.sh \
  --server http://<nightmend-host>:8001 \
  --token  <AGENT_REGISTER_TOKEN> \
  --name   $(hostname)
```

> 端口说明：后端容器内监听 `8000`，对外映射到宿主端口 `8001`（见 `docker-compose.yml` 的 `${BACKEND_PORT:-8001}:8000`）。**Agent 从主机网络访问，`--server` / `server.url` 一律填宿主端口 `8001`**，仅容器内部互访才用 `8000`。

脚本会：
1. 装 Python 3.9（如缺）+ 创建虚拟环境
2. 从本地 `agent/` 目录安装（不依赖 PyPI）
3. 生成 `/etc/nightmend/agent.yaml`
4. 注册 systemd 服务 `nightmend-agent.service`
5. 立即 `systemctl enable --now nightmend-agent`

#### 安装脚本参数

| 参数 | 简写 | 必填 | 说明 |
| --- | --- | --- | --- |
| `--server` | `-s` | ✅ | NightMend 后端地址，如 `http://192.168.1.100:8001` |
| `--token` | `-t` | ✅ | Agent Token（在「设置 → Agent Tokens」中获取） |
| `--hostname` | `-n` | ❌ | 自定义主机名，默认自动检测 |
| `--display-name` | — | ❌ | 自定义显示名称（在 NightMend 界面中显示） |
| `--interval` | `-i` | ❌ | 指标采集间隔（秒），默认 15 |
| `--no-db` | — | ❌ | 不安装数据库驱动，减小依赖体积 |
| `--upgrade` | — | ❌ | 升级已有安装，保留配置文件 |
| `--uninstall` | — | ❌ | 完全卸载 Agent |

### 3.2 CentOS 7 专用脚本

CentOS 7 的 Python 3 源较老，项目提供专用脚本：

```bash
cd /opt && git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend/agent
sudo bash install-agent-centos7.sh "http://<nightmend-host>:8001" "<AGENT_REGISTER_TOKEN>"
```

脚本动作：
- 备份 `/etc/yum.repos.d/` 现有配置
- 临时装 Python 3.9 仓库
- 用本地 agent 目录 `pip install` 离线安装
- 恢复原 yum 源

### 3.3 内网半自动安装（先手动装 Python 3.9+，再跑脚本）

适用于无法访问外网、或脚本自动安装 Python 失败的场景。先按发行版手动装好 Python 3.9+ 并换国内源，再执行 `scripts/install-agent.sh`（脚本会自动检测到已有 Python，跳过安装步骤）。

#### 第一步：按发行版安装 Python 3.9+

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

```bash
# 确保在 nightmend 仓库根目录
cd /path/to/nightmend

chmod +x ./scripts/install-agent.sh
sudo ./scripts/install-agent.sh \
  --server http://<nightmend-host>:8001 \
  --token  <AGENT_REGISTER_TOKEN> \
  --display-name "我的服务器"

# 验证
systemctl status nightmend-agent
journalctl -u nightmend-agent -f
```

### 3.4 手动安装

```bash
# 1. 装依赖
sudo apt install -y python3.10 python3.10-venv   # Ubuntu
# 或 sudo dnf install -y python3.11               # RHEL 9

# 2. 装 agent
python3 -m pip install --user nightmend-agent

# 3. 生成配置
sudo mkdir -p /etc/nightmend
sudo cp /path/to/agent.example.yaml /etc/nightmend/agent.yaml
# 编辑 server.url 和 server.token

# 4. 前台跑一次验证
nightmend-agent --config /etc/nightmend/agent.yaml

# 5. 装 systemd unit（可选）
sudo cp agent/scripts/nightmend-agent.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now nightmend-agent
```

---

## 四、Windows 安装

详见 `docs/windows-agent-install.md`。精华：

```powershell
# 1. 装 Python 3.11
winget install Python.Python.3.11

# 2. 装 agent
py -3.11 -m pip install nightmend-agent

# 3. 配置
New-Item -ItemType Directory -Path "C:\ProgramData\NightMend"
Copy-Item .\agent\agent.example.yaml "C:\ProgramData\NightMend\agent.yaml"

# 4. 装 Windows Service
py -3.11 -m nightmend_agent.install_service `
  --config "C:\ProgramData\NightMend\agent.yaml"

# 5. 启
sc start NightMendAgent
```

---

## 五、Agent 配置（`agent.yaml`）

```yaml
server:
  url: http://nightmend.example.com:8000
  token: "<AGENT_REGISTER_TOKEN>"        # 与后端 .env 一致
  tls_verify: true                        # https 生产环境必开

host:
  name: "web-01.example.com"              # 空则默认 hostname
  tags: ["production", "payments", "apac-1"]

metrics:
  interval: 15s                           # 最小 5s
  collectors: [cpu, mem, disk, net, proc, tcp, syslog]

services:
  - name: "payments-api"
    type: http
    url: http://127.0.0.1:8080/health
    interval: 30s
    timeout: 5s
    expect_status: 200

  - name: "postgres-local"
    type: tcp
    host: 127.0.0.1
    port: 5432

logs:
  - name: "app"
    path: /var/log/payments-api/app.log
    multiline: "^\\d{4}-\\d{2}-\\d{2}"

  - name: "journald-critical"
    type: journald
    units: ["nginx.service", "postgresql.service"]
    min_level: warning

databases:
  - name: "main-pg"
    type: postgres
    dsn: "postgres://nightmend_mon:<pwd>@127.0.0.1:5432/appdb?sslmode=disable"

  - name: "session-redis"
    type: redis
    dsn: "redis://127.0.0.1:6379/0"

gpu:
  enabled: true                           # 装了 nvidia-smi 才生效
  sample_rate: 5s
```

---

## 六、注册流程

1. Agent 启动 → POST `/api/v1/agents/register` 带 `AGENT_REGISTER_TOKEN`
2. 后端校验 token → 分配 agent_id + 长期 JWT
3. Agent 保存到 `/etc/nightmend/.agent-creds`
4. 后续上报走 `Bearer <JWT>`
5. 前端 `/hosts` 立即可见

手动触发重注册：
```bash
sudo rm /etc/nightmend/.agent-creds
sudo systemctl restart nightmend-agent
```

---

## 七、CLI 命令

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

## 八、Agent 模块说明

| 模块 | 文件 | 功能 |
| --- | --- | --- |
| 系统指标采集 | `collector.py` | 采集 CPU、内存、磁盘、网络 |
| 服务健康检查 | `checker.py` | HTTP / TCP 健康检查，记录响应时间 |
| 日志采集 | `log_collector.py` | Tail 日志，支持多行合并和 Docker json-log |
| 数据库指标 | `db_collector.py` | 采集 PostgreSQL / MySQL / Oracle 指标 |
| 自动发现 | `discovery.py` | 自动发现 Docker 容器和宿主机监听服务 |
| 数据上报 | `reporter.py` | 汇总数据，HTTP POST 上报到后端，处理自动更新 |
| 命令行入口 | `cli.py` | 提供 `run`、`check`、`configure` 等 CLI 命令 |
| 配置加载 | `config.py` | 解析 YAML 配置，支持环境变量覆盖 |

---

## 九、升级

### 自动升级（默认开启）

- Agent 定期（1h）询问后端当前版本
- 版本落后时下载 wheel 包到 `/var/lib/nightmend/updates/`
- 触发 `systemctl restart` 自身

### 手动升级

```bash
pipx upgrade nightmend-agent
sudo systemctl restart nightmend-agent
```

---

## 十、卸载

```bash
sudo systemctl disable --now nightmend-agent
pipx uninstall nightmend-agent
sudo rm -rf /etc/nightmend /var/lib/nightmend
```

Windows：
```powershell
sc stop NightMendAgent
py -3.11 -m nightmend_agent.uninstall_service
pip uninstall nightmend-agent
```

---

## 十一、故障排查

| 现象 | 排查 | 处置 |
| --- | --- | --- |
| Agent log 401 | token 错 | 重写 `agent.yaml` 的 `server.token` → `systemctl restart` |
| Agent 不上报 | 网络不通 | `curl -v http://<server>:8000/api/v1/health` |
| Agent 进程秒退 | Python 版本过低 | `nightmend-agent --version` 查 Python 要求 ≥ 3.9 |
| 指标重复 | 多个 agent 同名 | 改 `host.name` 保证唯一 |
| systemctl 看日志 | — | `journalctl -u nightmend-agent -f` |
| journald 无日志 | 无权限 | 把 agent 加入 `systemd-journal` 组 |
| TLS 验证失败 | 自签证书 | `tls_verify: false`（仅测试）或把 CA 加入系统信任 |
| GPU 不采集 | 驱动/nvidia-smi 缺 | `nvidia-smi --version` 验证 · 装 NVIDIA driver 470+ |

### 查日志

```bash
# systemd
journalctl -u nightmend-agent -f --since "10 min ago"

# agent 自身 log
tail -f /var/log/nightmend/agent.log

# 诊断模式（verbose）
nightmend-agent --config /etc/nightmend/agent.yaml --log-level debug
```

### 网络联调

```bash
# 1. DNS / 路由
getent hosts nightmend.example.com
traceroute nightmend.example.com

# 2. 后端端口
nc -zv nightmend.example.com 8000

# 3. TLS 握手
openssl s_client -connect nightmend.example.com:443 -servername nightmend.example.com

# 4. 注册接口
curl -v -X POST "http://<server>:8000/api/v1/agents/register" \
  -H "Content-Type: application/json" \
  -d '{"token":"<TOKEN>","hostname":"test"}'
```

---

## 十二、批量部署

### Ansible

```yaml
- hosts: all
  become: true
  tasks:
    - name: Sync NightMend agent payload
      synchronize:
        src: /opt/nightmend/agent/
        dest: /tmp/nightmend-agent/
        rsync_opts: ['--delete']
    - name: Install NightMend Agent
      shell: |
        cd /tmp/nightmend-agent && \
        bash scripts/install.sh \
          --server http://<server>:8000 \
          --token  {{ nightmend_token }} \
          --name   {{ inventory_hostname }}
      args:
        creates: /etc/nightmend/agent.yaml
```

### K8s DaemonSet

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: nightmend-agent
  namespace: monitoring
spec:
  selector: { matchLabels: { app: nightmend-agent } }
  template:
    metadata: { labels: { app: nightmend-agent } }
    spec:
      hostNetwork: true
      hostPID: true
      containers:
        - name: agent
          image: nightmend/agent:latest
          env:
            - name: NIGHTMEND_SERVER
              value: "http://nightmend.monitoring.svc:8000"
            - name: NIGHTMEND_TOKEN
              valueFrom:
                secretKeyRef: { name: nightmend-agent, key: token }
          volumeMounts:
            - { name: proc,   mountPath: /host/proc, readOnly: true }
            - { name: sys,    mountPath: /host/sys,  readOnly: true }
            - { name: rootfs, mountPath: /rootfs,    readOnly: true }
      volumes:
        - { name: proc,   hostPath: { path: /proc } }
        - { name: sys,    hostPath: { path: /sys  } }
        - { name: rootfs, hostPath: { path: /     } }
```

---

## 十三、相关文档

- 《用户手册》`docs/user-manual.md`
- 《部署手册》`docs/deployment.md`
- 《Windows Agent》`docs/windows-agent-install.md`
