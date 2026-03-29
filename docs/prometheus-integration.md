# VigilOps Prometheus 集成指南

VigilOps 提供了完整的 Prometheus 兼容性，支持两种集成方式：

## 1. 直接指标抓取（推荐）

VigilOps 暴露了标准的 `/api/v1/metrics` 端点，可直接被 Prometheus 抓取。

### Prometheus 配置

在 `prometheus.yml` 中添加以下配置：

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  # VigilOps 系统指标
  - job_name: 'vigilops'
    static_configs:
      - targets: ['vigilops-backend:8000']  # 或 localhost:8000
    metrics_path: '/api/v1/metrics'
    scrape_interval: 30s
    scrape_timeout: 10s

  # 可选：使用服务发现
  - job_name: 'vigilops-hosts'
    http_sd_configs:
      - url: 'http://vigilops-backend:8000/api/v1/prometheus/targets'
        refresh_interval: 60s
```

### 暴露的指标

VigilOps 提供以下 Prometheus 格式指标：

#### 主机性能指标
- `vigilops_host_cpu_percent{hostname, host_ip, group}` - CPU 使用百分比
- `vigilops_host_cpu_load_1m{hostname, host_ip, group}` - 1分钟负载平均值
- `vigilops_host_cpu_load_5m{hostname, host_ip, group}` - 5分钟负载平均值  
- `vigilops_host_cpu_load_15m{hostname, host_ip, group}` - 15分钟负载平均值
- `vigilops_host_memory_percent{hostname, host_ip, group}` - 内存使用百分比
- `vigilops_host_disk_percent{hostname, host_ip, group}` - 磁盘使用百分比
- `vigilops_host_network_bytes_sent_total{hostname, host_ip, group}` - 网络发送字节数
- `vigilops_host_network_bytes_received_total{hostname, host_ip, group}` - 网络接收字节数

#### 服务状态指标
- `vigilops_service_up{service_name, service_type, host_ip}` - 服务状态 (1=运行, 0=停止)
- `vigilops_service_response_time_seconds{service_name, service_type, host_ip}` - 响应时间(秒)

#### 告警统计指标
- `vigilops_alerts_total{status, severity}` - 按状态和严重级别分组的告警数量
- `vigilops_hosts_total` - 监控的主机总数
- `vigilops_hosts_by_status{status}` - 按状态分组的主机数量
- `vigilops_services_total` - 监控的服务总数

#### 系统状态指标
- `vigilops_up{version}` - VigilOps 系统可用性
- `vigilops_last_scrape_timestamp_ms` - 最后抓取时间戳

## 2. 查询示例

### Grafana Dashboard

```promql
# CPU 使用率 Top 10 主机
topk(10, vigilops_host_cpu_percent)

# 内存使用率超过 80% 的主机
vigilops_host_memory_percent > 80

# 服务可用率
avg_over_time(vigilops_service_up[5m]) * 100

# 告警趋势
rate(vigilops_alerts_total[5m])
```

### 告警规则

```yaml
# prometheus-rules.yml
groups:
  - name: vigilops.rules
    rules:
      - alert: HostHighCPU
        expr: vigilops_host_cpu_percent > 90
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "主机 {{ $labels.hostname }} CPU 使用率过高"
          description: "主机 {{ $labels.hostname }} CPU 使用率为 {{ $value }}%，超过 90%"

      - alert: ServiceDown
        expr: vigilops_service_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "服务 {{ $labels.service_name }} 不可用"
          description: "服务 {{ $labels.service_name }} 在主机 {{ $labels.host_ip }} 上不可用"

      - alert: VigilOpsDown
        expr: vigilops_up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "VigilOps 系统不可用"
          description: "VigilOps 监控系统无法访问"
```

## 3. Docker Compose 集成示例

```yaml
# docker-compose.yml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus-rules.yml:/etc/prometheus/rules.yml
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'
      - '--web.console.libraries=/etc/prometheus/console_libraries'
      - '--web.console.templates=/etc/prometheus/consoles'
      - '--storage.tsdb.retention.time=200h'
      - '--web.enable-lifecycle'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-storage:/var/lib/grafana

  vigilops-backend:
    image: vigilops:latest
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://...
      - REDIS_URL=redis://...

volumes:
  grafana-storage:
```

## 4. 高级功能

### 服务发现

VigilOps 提供 HTTP 服务发现端点 `/api/v1/prometheus/targets`，自动发现监控目标：

```yaml
scrape_configs:
  - job_name: 'vigilops-discovered'
    http_sd_configs:
      - url: 'http://vigilops-backend:8000/api/v1/prometheus/targets'
        refresh_interval: 60s
```

### 认证支持

如果 VigilOps 启用了认证，需要配置 Bearer Token：

```yaml
scrape_configs:
  - job_name: 'vigilops'
    static_configs:
      - targets: ['vigilops-backend:8000']
    metrics_path: '/api/v1/metrics'
    authorization:
      type: Bearer
      credentials: 'your-api-token'
```

## 5. 故障排除

### 常见问题

1. **指标端点不可访问**
   - 检查 VigilOps 后端是否正常运行
   - 确认端口 8000 可访问
   - 检查防火墙设置

2. **指标数据为空**
   - 确认 VigilOps 已收集到监控数据
   - 检查数据库连接是否正常
   - 查看 VigilOps 后端日志

3. **Prometheus 抓取失败**
   - 检查 Prometheus 配置语法
   - 确认目标地址正确
   - 查看 Prometheus targets 页面状态

### 测试命令

```bash
# 测试指标端点
curl http://localhost:8000/api/v1/metrics

# 测试服务发现
curl http://localhost:8000/api/v1/prometheus/targets

# 检查 Prometheus 目标状态
curl http://localhost:9090/api/v1/targets
```

## 6. 最佳实践

1. **抓取间隔**: 建议设置为 30-60 秒，避免过于频繁
2. **数据保留**: 根据需求设置 Prometheus 数据保留时间
3. **高可用**: 使用 Prometheus 集群模式提高可靠性
4. **告警规则**: 设置合理的告警阈值和持续时间
5. **监控监控**: 监控 Prometheus 和 VigilOps 的健康状态

通过以上配置，您可以将 VigilOps 无缝集成到现有的 Prometheus 监控体系中，实现统一的监控数据收集和告警管理。

---

## 7. AlertManager Webhook 集成（v2026.03.29 新增）

VigilOps 可以接收 Prometheus AlertManager 的告警推送，实现 **AI 自动诊断 + 可选自动修复**。

### AlertManager 配置

在 AlertManager 的 `alertmanager.yml` 中添加 VigilOps 作为 webhook receiver：

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m

route:
  receiver: 'vigilops'
  group_by: ['alertname', 'instance']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h

receivers:
  - name: 'vigilops'
    webhook_configs:
      - url: 'http://vigilops-backend:8000/api/v1/webhooks/alertmanager'
        send_resolved: true
        http_config:
          authorization:
            type: Bearer
            credentials: '<your-webhook-token>'
```

### VigilOps 环境变量

在 `.env` 中配置以下参数：

```bash
# AlertManager Webhook 认证令牌
ALERTMANAGER_WEBHOOK_TOKEN=your-secure-token

# 可选：HMAC 签名验证密钥（如果 AlertManager 配置了 HMAC）
ALERTMANAGER_HMAC_SECRET=your-hmac-secret

# 诊断模式：仅运行 AI 分析，不执行自动修复
ENABLE_REMEDIATION=false
```

### 工作流程

1. AlertManager 检测到告警 → 通过 webhook 推送到 VigilOps
2. VigilOps 验证 Bearer Token + 可选 HMAC 签名
3. Redis 去重防止重复告警处理
4. `PrometheusAdapter` 解析告警并映射到 VigilOps 主机
5. AI 引擎进行根因分析，生成诊断结果
6. 如果 `ENABLE_REMEDIATION=true`，匹配 Runbook 并执行自动修复

### 诊断演示模式

设置 `ENABLE_REMEDIATION=false` 后，VigilOps 只运行 AI 诊断，不执行任何修复命令。适合初期评估。

访问 `/demo` 页面可以：
- 查看 AlertManager 配置片段
- 实时观看告警流 + AI 诊断结果（SSE）
- 无需登录