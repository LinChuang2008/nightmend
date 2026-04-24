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
sudo bash scripts/install.sh \
  --server http://<nightmend-host>:8000 \
  --token  <AGENT_REGISTER_TOKEN> \
  --name   $(hostname)
```

脚本会：
1. 装 Python 3.9（如缺）+ `pipx`
2. `pipx install .`（用本地 wheel，不依赖 PyPI）
3. 生成 `/etc/nightmend/agent.yaml`
4. 注册 systemd 服务 `nightmend-agent.service`
5. 立即 `systemctl enable --now nightmend-agent`

### 3.2 CentOS 7 专用脚本

CentOS 7 的 Python 3 源较老，项目提供专用脚本：

```bash
cd /opt && git clone https://github.com/LinChuang2008/nightmend.git
cd nightmend/agent
sudo bash install-agent-centos7.sh "http://<nightmend-host>:8000" "<AGENT_REGISTER_TOKEN>"
```

脚本动作：
- 备份 `/etc/yum.repos.d/` 现有配置
- 临时装 Python 3.9 仓库
- 用本地 agent 目录 `pip install` 离线安装
- 恢复原 yum 源

### 3.3 手动安装

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

## 七、升级

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

## 八、卸载

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

## 九、故障排查

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

## 十、批量部署

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

## 十一、相关文档

- 《用户手册》`docs/USER_MANUAL.md`
- 《部署手册》`docs/DEPLOYMENT_MANUAL.md`
- 《Windows Agent》`docs/windows-agent-install.md`
- 《Agent 使用细节》`docs/agent-guide.md`
