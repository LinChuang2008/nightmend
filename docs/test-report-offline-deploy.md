# NightMend 离线部署端到端测试报告

- **测试日期**: 2026-02-20
- **测试环境**: 阿里云 ECS demo.lchuangnet.com (CentOS Stream 9, 8核15GB)
- **测试方式**: 方案 B（安全验证，不启动容器避免端口冲突）
- **测试包**: nightmend-deploy.tar.gz (86MB)

---

## 测试结果总览

| # | 检查项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | tar 包完整性 | ✅ PASS | 含 docker-compose.yml, install.sh, init.sh, backend.tar.gz, frontend.tar.gz |
| 2 | docker load backend | ✅ PASS | nightmend-backend:latest (239MB) |
| 3 | docker load frontend | ✅ PASS | nightmend-frontend:latest (26.2MB) |
| 4 | install.sh 语法检查 | ✅ PASS | bash -n 通过 |
| 5 | .env 文件生成 | ❌ FAIL | .env.example 未打包进 tar，无法生成 .env |
| 6 | docker-compose.yml 离线可用 | ❌ FAIL | 仍使用 `build:` 而非 `image:`，离线环境无源码无法构建 |
| 7 | migration SQL 完整性 | ⚠️ WARN | 缺少 001_init.sql；存在编号冲突 (两个 012, 两个 013) |
| 8 | install.sh --help | ❌ FAIL | 无 --help 支持，直接执行部署 |
| 9 | 自定义端口支持 | ❌ FAIL | 端口硬编码在 docker-compose.yml，install.sh 无端口参数 |
| 10 | 卸载功能 | ❌ FAIL | 无 uninstall.sh 或 install.sh --uninstall |

---

## 发现的问题

### BUG-1: .env.example 未打包进部署 tar (P0 - 阻断)

**描述**: nightmend-deploy.tar.gz 不含 .env.example 文件。install.sh 在无 .env.example 时仅输出 warning 继续执行，但 docker-compose.yml 的 `env_file: .env` 导致直接报错退出。

**复现**: 解压 tar → 运行 install.sh → `env file .env not found` 错误

**修复**: 打包时加入 .env.example，或 install.sh 内联生成默认 .env。

---

### BUG-2: docker-compose.yml 使用 build: 而非 image: (P0 - 阻断)

**描述**: docker-compose.yml 中 backend 和 frontend 服务使用 `build: ./backend` / `build: ./frontend`，但离线 tar 包内无源码目录，只有预构建镜像。docker compose up 会因找不到 build context 而失败。

**修复**: install.sh 应将 docker-compose.yml 中的 `build:` 替换为 `image: nightmend-backend:latest` / `image: nightmend-frontend:latest`，或打包一份离线专用 docker-compose.yml。

---

### BUG-3: 不支持自定义端口 (P1)

**描述**: 端口 (8001/3001/5433/6380) 硬编码在 docker-compose.yml。客户环境如有端口冲突无法调整。install.sh 无任何参数支持。

**修复**: docker-compose.yml 用 `${BACKEND_PORT:-8001}:8000` 等环境变量；install.sh 提供交互式或 `--port` 参数。

---

### BUG-4: Migration SQL 编号冲突 (P1)

**描述**: 
- 两个 012: `012_service_category.sql` 和 `012_service_topology.sql`
- 两个 013: `013_sla.sql` 和 `013_topology_layout.sql`
- 缺少 001_init.sql（建表基础脚本）

编号冲突可能导致 migration 执行顺序不确定。

**修复**: 重新编号，确保唯一递增；补充 001_init.sql。

---

### BUG-5: 无 --help 和卸载功能 (P2)

**描述**: install.sh 不支持 `--help`（直接执行部署）、无 `--uninstall`。客户体验差，无法预览安装行为或清理。

**修复**: 添加参数解析：`--help`, `--uninstall`, `--check`(仅检查不安装)。

---

### BUG-6: init.sh 硬编码端口与实际不符 (P2)

**描述**: init.sh 最后输出 `Frontend: http://localhost:3000` 和 `Backend: http://localhost:8000`，但实际映射端口为 3001 和 8001。

**修复**: 输出应与 docker-compose.yml 端口映射一致。

---

## 结论

**当前离线部署包无法被客户直接使用**，存在 2 个 P0 阻断级 bug（缺 .env.example、docker-compose 用 build 而非 image）。客户解压后运行 install.sh 必定失败。

### 修复优先级
1. **P0**: 打包 .env.example + 离线 docker-compose.yml 使用 image 而非 build
2. **P1**: 支持自定义端口 + 修复 migration 编号冲突
3. **P2**: 添加 --help/--uninstall + 修复 init.sh 端口显示
