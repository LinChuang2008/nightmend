# 日志后端配置指南 (Log Backend Configuration Guide)

NightMend 支持多种高性能日志存储后端，可根据数据量和性能需求灵活选择。

## 支持的后端类型

### 1. PostgreSQL (默认)
- **适用场景**: 小到中等规模部署 (< 10万条日志/天)
- **优势**: 开箱即用，完全兼容，支持复杂查询
- **劣势**: 大量日志时性能下降，存储成本高

### 2. ClickHouse (推荐)
- **适用场景**: 中大规模部署 (> 10万条日志/天)
- **优势**: 极高的写入性能，压缩率高，查询速度快
- **劣势**: 需要额外部署，内存占用较高

### 3. Loki (开发中)
- **适用场景**: Grafana 生态集成，云原生部署
- **优势**: 与 Grafana 无缝集成，标签化查询
- **劣势**: 功能相对简单，性能中等

## 配置方法

### 环境变量配置

在 `.env` 文件中添加以下配置：

```bash
# 日志后端类型 (postgresql/clickhouse/loki)
LOG_BACKEND_TYPE=clickhouse

# 日志保留天数
LOG_RETENTION_DAYS=30

# ClickHouse 配置
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=default
CLICKHOUSE_PASSWORD=
CLICKHOUSE_DATABASE=nightmend

# Loki 配置 (如果使用)
LOKI_URL=http://localhost:3100
LOKI_USERNAME=
LOKI_PASSWORD=
```

### Docker Compose 部署

#### ClickHouse 后端

```yaml
services:
  # ... 其他服务 ...

  clickhouse:
    image: clickhouse/clickhouse-server:24.1-alpine
    ports:
      - "8123:8123"
      - "9000:9000"
    environment:
      CLICKHOUSE_DB: nightmend
      CLICKHOUSE_USER: default
      CLICKHOUSE_PASSWORD: ""
    volumes:
      - clickhousedata:/var/lib/clickhouse
      - ./clickhouse-config:/etc/clickhouse-server/conf.d
    restart: unless-stopped

volumes:
  clickhousedata:
```

#### Loki 后端

```yaml
services:
  # ... 其他服务 ...

  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    command: -config.file=/etc/loki/local-config.yaml
    volumes:
      - lokidata:/loki
    restart: unless-stopped

volumes:
  lokidata:
```

## 数据迁移

### 使用脚本迁移

```bash
# 从 PostgreSQL 迁移到 ClickHouse
cd /path/to/nightmend
python scripts/migrate_logs.py --source postgresql --target clickhouse

# 检查迁移计划 (不实际迁移数据)
python scripts/migrate_logs.py --source postgresql --target clickhouse --dry-run

# 自定义批处理大小
python scripts/migrate_logs.py --source postgresql --target clickhouse --batch-size 5000

# 迁移特定时间范围的数据
python scripts/migrate_logs.py --source postgresql --target clickhouse \
                               --start-date 2024-01-01 --end-date 2024-01-31
```

### 使用 API 迁移

```bash
# 健康检查
curl -X GET "http://localhost:8001/api/v1/admin/logs/health" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# 执行迁移
curl -X POST "http://localhost:8001/api/v1/admin/logs/migrate?source=postgresql&target=clickhouse" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# 查看配置
curl -X GET "http://localhost:8001/api/v1/admin/logs/config" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

## 性能对比

| 后端 | 写入性能 | 查询性能 | 存储压缩 | 内存使用 |
|------|----------|----------|----------|----------|
| PostgreSQL | 中等 | 中等 | 低 | 中等 |
| ClickHouse | 极高 | 高 | 高 | 高 |
| Loki | 高 | 中等 | 中等 | 低 |

### ClickHouse 性能调优

1. **分区策略**: 按月分区，自动清理过期分区
2. **索引优化**: 时间戳 + 主机ID + 日志级别的复合排序键
3. **内存设置**: 建议至少 4GB 内存，8GB+ 最佳
4. **写入优化**: 启用异步插入，批量写入

```xml
<!-- clickhouse-config/performance.xml -->
<yandex>
    <profiles>
        <logs_insert>
            <async_insert>1</async_insert>
            <wait_for_async_insert>0</wait_for_async_insert>
            <async_insert_max_data_size>10485760</async_insert_max_data_size>
            <async_insert_busy_timeout_ms>200</async_insert_busy_timeout_ms>
        </logs_insert>
    </profiles>
</yandex>
```

## 故障转移和高可用

### 自动故障转移

NightMend 支持自动故障转移：

1. **主后端**: 配置的高性能后端 (如 ClickHouse)
2. **备用后端**: PostgreSQL (总是可用)
3. **故障检测**: 定期健康检查，自动切换

### 双写模式

在迁移期间，可以启用双写模式：

```python
# 在 log_service.py 中配置
ENABLE_DUAL_WRITE = True  # 同时写入两个后端
```

## 监控和维护

### 日志清理

```bash
# 手动清理过期日志 (保留7天)
curl -X POST "http://localhost:8001/api/v1/admin/logs/cleanup?retention_days=7" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# 查看后端统计
curl -X GET "http://localhost:8001/api/v1/admin/logs/stats" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### 性能测试

```bash
# 测试写入性能 (写入1000条测试日志)
curl -X POST "http://localhost:8001/api/v1/admin/logs/test-store?count=1000" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN"

# 查看性能指标
curl -X GET "http://localhost:8001/api/v1/admin/logs/performance?hours=24" \
     -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

## 最佳实践

### 1. 容量规划

- **小规模** (< 1万条/天): PostgreSQL
- **中规模** (1万-10万条/天): ClickHouse 单节点
- **大规模** (> 10万条/天): ClickHouse 集群

### 2. 数据保留策略

根据业务需求设置合适的保留期：

```bash
# 开发环境: 3天
LOG_RETENTION_DAYS=3

# 生产环境: 30-90天
LOG_RETENTION_DAYS=30

# 合规要求: 1年
LOG_RETENTION_DAYS=365
```

### 3. 索引策略

ClickHouse 主键设计：

```sql
ORDER BY (timestamp, host_id, level)
PARTITION BY toYYYYMM(timestamp)
```

### 4. 备份策略

- **PostgreSQL**: 使用 pg_dump 定期备份
- **ClickHouse**: 使用 clickhouse-backup 工具
- **配置备份**: 定期备份配置文件和迁移脚本

## 故障排除

### 常见问题

1. **ClickHouse 连接失败**
   - 检查防火墙设置 (8123 端口)
   - 验证用户名密码
   - 检查 Docker 容器状态

2. **写入性能差**
   - 检查批处理大小设置
   - 验证内存配置
   - 查看 ClickHouse 日志

3. **查询超时**
   - 增加查询超时时间
   - 检查索引使用情况
   - 优化查询条件

### 日志位置

- **应用日志**: `/var/log/nightmend/`
- **ClickHouse 日志**: `/var/log/clickhouse-server/`
- **Loki 日志**: Docker 容器日志

### 调试命令

```bash
# 检查后端连通性
curl "http://localhost:8123" -d "SELECT 1"

# 查看 ClickHouse 系统表
curl "http://localhost:8123" -d "SELECT * FROM system.databases"

# 测试日志查询
curl "http://localhost:8001/api/v1/logs?q=error&page_size=10" \
     -H "Authorization: Bearer YOUR_TOKEN"
```

## 升级指南

### 从 PostgreSQL 升级到 ClickHouse

1. **准备环境**
   ```bash
   docker-compose up -d clickhouse
   ```

2. **更新配置**
   ```bash
   echo "LOG_BACKEND_TYPE=clickhouse" >> .env
   ```

3. **执行迁移**
   ```bash
   python scripts/migrate_logs.py --source postgresql --target clickhouse --dry-run
   python scripts/migrate_logs.py --source postgresql --target clickhouse
   ```

4. **验证迁移**
   ```bash
   curl -X GET "http://localhost:8001/api/v1/admin/logs/health"
   ```

5. **重启应用**
   ```bash
   docker-compose restart backend
   ```

### 回退方案

如需回退到 PostgreSQL：

```bash
echo "LOG_BACKEND_TYPE=postgresql" >> .env
docker-compose restart backend
```

数据会自动从 PostgreSQL 读取（已有数据不受影响）。