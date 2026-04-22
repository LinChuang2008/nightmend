# NightMend 用户手册

> 版本 v1.1 · 更新 2026-04-22
> 产品定位：AI 驱动的基础设施监控平台 —— 不只检测告警，还自动诊断并修复

---

## 一、账号与登录

- 访问地址：`http://<your-host>:3001`
- 演示账号：`demo@vigilops.io` / `demo123`（只读 Demo）
- 登录方式：
  - 邮箱 + 密码
  - LDAP（企业目录）
  - Google / GitHub（如在服务器端开启 SSO）
  - SAML / Azure AD / Okta（企业 SSO）

登录后首次访问会出现新手引导弹窗，一路「下一步」即可关闭。

---

## 二、导航结构（4 分组 · 27 个入口）

左侧主菜单分为 4 个业务域：

### 1. 监控（Monitoring）

| 菜单 | 路由 | 用途 |
| --- | --- | --- |
| 仪表盘 | `/dashboard` | 核心 KPI + 告警流 + 健康评分 |
| 服务器 | `/hosts` | 全量主机列表 / 详情 |
| 服务监控 | `/services` | 业务服务 up/down 探测 |
| 服务拓扑 | `/topology` | 管道分层视图（接入/应用/中间件/数据） |
| 拓扑服务器 | `/topology/servers` | 服务器视角拓扑 |
| 服务组 | `/topology/service-groups` | 按逻辑分组 |
| 日志管理 | `/logs` | 全文搜索 + 级别筛选 |
| 数据库监控 | `/databases` | PG / MySQL / Redis 等 |

### 2. 告警（Alerts）

| 菜单 | 路由 | 用途 |
| --- | --- | --- |
| 告警中心 | `/alerts` | 活跃告警 + 规则 + 降噪 |
| 告警升级 | `/alert-escalation` | 升级策略 |
| 值班排期 | `/on-call` | 轮值表 |
| SLA | `/sla` | SLO 达成率 |

### 3. 分析 · AI Ops

| 菜单 | 路由 | 用途 |
| --- | --- | --- |
| AI 分析 | `/ops` | OpsAssistant 智能诊断 |
| AI 操作日志 | `/ai-operation-logs` | AI 决策审计 |
| 自动修复 | `/remediations` | 运行中 / 历史修复任务 |
| Runbook | `/runbooks` | 可执行的修复剧本库 |
| 报告 | `/reports` | SLA / 容量 / 故障报告 |

### 4. 配置

| 菜单 | 路由 | 用途 |
| --- | --- | --- |
| 通知渠道 | `/notification-channels` | 邮件 / 飞书 / 钉钉 / Slack |
| 通知模板 | `/notification-templates` | 自定义告警文案 |
| 通知日志 | `/notification-logs` | 发送审计 |
| 用户 | `/users` | 角色权限 |
| 审计日志 | `/audit-logs` | 管理操作追溯 |
| AI 配置 | `/ai-configs` | 模型 / Prompt |
| 设置 | `/settings` | 全局参数 |

---

## 三、常用业务场景

### 场景 A · 查看当前健康状况

1. 登录后默认落 `/dashboard`
2. 关注 3 个核心指标：
   - **健康评分**（右上环形仪表盘）：≥85 绿 · 70–85 黄 · <70 红
   - **活跃告警**（KPI 卡）：当前 firing 数
   - **服务器离线**（KPI 卡）：掉线主机
3. 点击「服务器健康总览」任意主机进入详情页
4. 指标实时更新（WebSocket · 10s 一次）

### 场景 B · 处理新告警

路径：`/alerts`

1. 表格按严重度排序，严重度用 mono chip + glow dot 标识
2. 点击告警行「详情」打开 Drawer：
   - **AI 因果图**：自动推断上下游影响链
   - **建议 Runbook**：匹配度 + 一键执行（需审批）
   - **相关事件时间线**：最近 24h 关联
3. 操作按钮：
   - 「确认」：自己接手
   - 「升级」：转交二级
   - 「静默 15min」：短暂抑制
   - 「▶ 执行修复」：运行匹配的 Runbook（自动模式需审批）

### 场景 C · 分析业务拓扑

路径：`/topology`

1. 默认「管道」视图 —— 4 列从左到右：**接入层 → 应用层 → 中间件 → 数据层**
2. 系统按服务名智能归类（redis/memcache 落缓存、mysql/pg 落数据层、nginx/traefik 落接入层、kafka/rabbit 落中间件……）
3. 节点状态一目了然：
   - 绿色 glow dot · healthy
   - 黄色 · warning
   - 红色 · critical
4. 管道模式强制按 stage 列归位以保证分层清晰
5. 「力导向」模式切换到自由布局，适合看调用关系

### 场景 D · 查日志

路径：`/logs`

1. 左上「搜索 / 实时日志」切换
2. 筛选：服务器 · 服务 · 日志级别（DEBUG / INFO / WARN / ERROR / FATAL）· 时间窗
3. 级别 chip 带 glow（WARN 黄 / ERROR 红 / FATAL 亮粉）
4. 点击行展开详情 · 原始 JSON 块支持复制

### 场景 E · AI 诊断

路径：`/ops`

1. 自然语言提问：「为什么 checkout 在 14:18 出 5xx？」
2. Ops Assistant 会：
   - 拉取时段内 metrics / traces / logs
   - 定位根因并给出证据（每条引用可点开）
   - 推荐已批准的 Runbook
3. 所有回答都标注了数据来源（alert / trace / deploy），可追溯

---

## 四、键盘 / 效率小技巧

| 操作 | 快捷键 |
| --- | --- |
| 全局搜索 | `⌘K` / `Ctrl+K` |
| 刷新页面 | `F5` |
| 切语言 | 右上 🌐 图标 |
| 切明 / 暗主题 | 右上 ☀/🌙（当前强制暗色，可改配置） |
| 关闭引导层 | 右上 ×  或  页面空白点一下 |

---

## 五、权限角色

| 角色 | 能做什么 |
| --- | --- |
| Admin | 全部 + 用户 / AI 配置 / 审计 |
| Operator | 主机 / 告警 / Runbook 执行 |
| Viewer | 只读 |
| Demo | 只读（不能发短信 / 实际修复） |

角色由管理员在 `/users` 指派。新用户默认 `Viewer`。

---

## 六、数据范围与保留

- **指标**：10s 原始粒度，30 天热存储 + 2 年冷存储
- **日志**：Loki 后端 · 默认 30 天（可在 `/settings` 调整）
- **告警**：永久，已 resolved 90 天后归档
- **AI 对话**：按租户隔离 · 90 天
- **审计**：180 天

---

## 七、故障排除

| 现象 | 可能原因 | 处置 |
| --- | --- | --- |
| 页面一直转圈 | 后端或 WebSocket 未启动 | 看浏览器 Console 的 API 500/401 |
| 告警迟到 | 规则未启用 / 主机掉线 | `/alerts` → 规则 Tab 检查 `is_enabled` |
| Agent 不上报 | token 错 / 网络不通 | 见《Agent 安装手册》§ 6 |
| 登录 401 | 密码错 / 被限流 | 5 次错试会冻结 5 分钟 |
| 分页显示 `{{count}}` | 旧版 bug | 升到 v1.1（已修） |

---

## 八、更多文档

- 部署手册：`docs/DEPLOYMENT_MANUAL.md`
- Agent 安装：`docs/AGENT_INSTALL.md`
- API 参考：`docs/api-reference.md`
- FAQ：`docs/faq.md`
- Prometheus 对接：`docs/prometheus-integration.md`
