# NightMend 部署手册

> 版本 v1.1 · 更新 2026-04-22
> 覆盖：单机 Docker Compose · 生产加固 · HTTPS · 升级 · 备份 · 卸载

---

## 一、系统要求

| 组件 | 最低 | 推荐（生产） |
| --- | --- | --- |
| CPU | 2 核 | 8 核+ |
| 内存 | 4 GB | 16 GB+ |
| 磁盘 | 40 GB SSD | 200 GB+ NVMe（指标/日志增长快） |
| 操作系统 | Ubuntu 20.04 / CentOS 7 / Debian 11 / RHEL 8+ | Ubuntu 22.04 LTS |
| Docker | 24.0+ | 25.0+ |
| Docker Compose | v2.20+（插件形态） | v2.29+ |
| 端口 | 3001 (前端) · 8000 (后端) · 5432 (pg) · 6379 (redis) · 8003 (mcp) | 同左 + 443 反代 |

支持架构：`amd64`、`arm64`

---

## 二、一键部署（基于仓库内脚本）

> 目前没有公网 installer 域名，部署需要先把仓库拉到目标机。

```bash
# 1. 克隆仓库（内网 gitlab 或 GitHub）
git clone https://gitlab.lchuangnet.com/lchuangnet/nightmend.git /opt/nightmend
# 或（外网）
git clone https://github.com/LinChuang2008/nightmend.git /opt/nightmend

# 2. 执行仓库内的安装脚本
cd /opt/nightmend
sudo ./install.sh

# 3. 可选参数
sudo ./install.sh --dir=/opt/nightmend --branch=main
```

脚本动作（见 `install.sh` 源码）：
1. 校验 Docker / Docker Compose 版本
2. 生成 `.env`（随机 `POSTGRES_PASSWORD` / `JWT_SECRET` / `AGENT_REGISTER_TOKEN`）
3. `docker compose pull` + `docker compose up -d`
4. 打印访问地址与初始 admin 密码

> 如果只想最小化启动（已有 `.env`），直接 `docker compose up -d` 即可。

---

## 三、手动部署（五步）

### 1. 拉取仓库
```bash
git clone https://github.com/LinChuang2008/nightmend.git /opt/nightmend
cd /opt/nightmend
```

### 2. 写 `.env`
```bash
cp .env.example .env
# 至少修改：
#   POSTGRES_PASSWORD    # 32 位随机
#   JWT_SECRET           # 64 位随机
#   AGENT_REGISTER_TOKEN # agent 注册 token
#   FRONTEND_PORT=3001
#   PUBLIC_URL=http://your-host:3001
```

### 3. 启动
```bash
docker compose up -d
```

服务清单（`docker compose ps`）：

| 容器 | 端口 | 作用 |
| --- | --- | --- |
| `nightmend-postgres-1` | 5432 | 元数据存储 |
| `nightmend-redis-1` | 6379 | 缓存 + 队列 |
| `nightmend-clickhouse-1` | 8123/9000 | 指标 OLAP |
| `nightmend-loki-1` | 3100 | 日志存储 |
| `nightmend-backend-1` | 8000 | FastAPI 主业务 |
| `nightmend-mcp-1` | 8003 | Model Context Protocol server |
| `nightmend-frontend-1` | 3001 → 80 | Nginx + React 静态资源 |

### 4. 初始化数据库
```bash
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.scripts.seed_demo   # 可选 demo 数据
```

### 5. 访问与首次登录
- 前端：`http://<host>:3001`
- 初始管理员：`.env` 里 `ADMIN_EMAIL` / 首次启动 log 打印的 `ADMIN_PASSWORD`
- 登录后立即改密 + 新建组织成员

---

## 四、生产环境加固

### 1. 反向代理 + HTTPS

```bash
docker compose -f docker-compose.yml -f docker-compose.ssl.yml up -d
```

或自备 nginx / traefik，参考 `docs/HTTPS.md`。

### 2. 环境变量必改项

```env
POSTGRES_PASSWORD=<32-char-random>
JWT_SECRET=<64-char-random>
AGENT_REGISTER_TOKEN=<secret>

PUBLIC_URL=https://monitor.example.com
CORS_ORIGINS=https://monitor.example.com

ENABLE_DEMO_ACCOUNT=false

SMTP_HOST=...
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
```

### 3. 资源限制（示例）

```yaml
# docker-compose.prod.yml
services:
  backend:
    deploy:
      resources:
        limits:       { cpus: '4', memory: 4G }
        reservations: { cpus: '2', memory: 2G }
  clickhouse:
    deploy:
      resources:
        limits:       { cpus: '4', memory: 8G }
```

### 4. 防火墙

仅开放 443 + 22；内部端口用 Docker 默认 bridge 隔离。

### 5. 日志轮转

```json
// /etc/docker/daemon.json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "100m",
    "max-file": "5"
  }
}
```

```bash
systemctl restart docker
```

---

## 五、升级

### 快速升级（基于本地脚本）
```bash
cd /opt/nightmend
sudo ./install.sh --upgrade
```

### 手动升级
```bash
cd /opt/nightmend
git fetch --all
git checkout main && git pull
docker compose pull
docker compose up -d
docker compose exec backend alembic upgrade head   # 如有 migration
```

### 回滚
```bash
cd /opt/nightmend
git checkout <previous-tag>
docker compose up -d --force-recreate
# 如有不可回滚的迁移，先从备份恢复
```

---

## 六、备份与恢复

### 自动备份
```bash
# crontab 每天 03:00
0 3 * * * /opt/nightmend/scripts/backup.sh
```

产物：`backups/YYYY-MM-DD.tar.gz`，含：
- `pg_dump` PG 数据
- `clickhouse-backup` 增量
- `.env` + `docker-compose.yml`

### 恢复
```bash
cd /opt/nightmend
tar xzf backups/2026-04-22.tar.gz -C /tmp/restore
./scripts/restore.sh /tmp/restore
```

---

## 七、自身健康监控

| 端点 | 作用 |
| --- | --- |
| `GET /api/v1/health` | 后端存活 |
| `GET /api/v1/health/deep` | 依赖全链路（PG / Redis / Clickhouse / Loki） |
| `GET /health` （前端 nginx） | 静态资源可达 |
| `GET :9090/metrics` | Prometheus 格式指标（可选） |

---

## 八、卸载

```bash
cd /opt/nightmend
docker compose down -v          # 删容器 + 数据卷（不可逆）
cd .. && rm -rf nightmend
```

如仅停服务保留数据：
```bash
docker compose down             # 保留 volumes
```

---

## 九、常见部署问题

| 现象 | 原因 | 处置 |
| --- | --- | --- |
| `frontend` exit 1 | 前端构建失败 | 查 `docker compose logs frontend` |
| `backend` 启动卡住 | alembic migration 错 | `docker compose exec backend alembic current` 查进度 |
| Agent 连不上 | token 错 / 防火墙 | 见 AGENT_INSTALL § 6 |
| Clickhouse 占盘 | 留存太久 | 改 `.env CLICKHOUSE_TTL_DAYS` 然后 `OPTIMIZE FINAL` |
| 前端 502 | 后端没就绪 / 代理配置错 | `nginx.conf` 内 upstream 指 `backend:8000` |

---

## 十、离线 / 气隙部署

1. 联网机执行 `./scripts/bundle-offline.sh` → 生成 `nightmend-offline-<date>.tar`
2. 复制到气隙机
3. `tar xf nightmend-offline-<date>.tar && cd nightmend-offline && ./install.sh`
4. 脚本用本地镜像仓库，不走外网

详见 `docs/test-report-offline-deploy.md`。

---

## 十一、相关文档

- 《用户手册》`docs/USER_MANUAL.md`
- 《Agent 安装手册》`docs/AGENT_INSTALL.md`
- 《HTTPS 配置》`docs/HTTPS.md`
- 《架构概览》`docs/architecture.md`
- 《API 参考》`docs/api-reference.md`
