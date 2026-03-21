---
name: redis-troubleshoot
description: Redis 内存、连接与性能问题排查
triggers:
  - redis
  - 缓存
  - cache
  - oom
  - maxmemory
  - 连接拒绝
  - connection refused
---

# Redis 排障技能

## 适用场景
Redis 内存溢出、连接数超限、慢命令、持久化问题、主从同步异常等。

## 常用诊断命令

### 查看 Redis 整体状态
```bash
redis-cli info server | grep -E "redis_version|uptime|hz"
redis-cli info memory | grep -E "used_memory_human|maxmemory_human|mem_fragmentation_ratio"
redis-cli info clients | grep -E "connected_clients|blocked_clients"
redis-cli info stats | grep -E "total_commands|rejected_connections|evicted_keys"
```

### 查看慢日志
```bash
redis-cli slowlog get 20
redis-cli slowlog len
```

### 查看 Key 分布
```bash
redis-cli info keyspace
redis-cli dbsize
redis-cli --bigkeys 2>/dev/null | tail -30
```

### 查看持久化状态
```bash
redis-cli info persistence | grep -E "rdb_|aof_"
redis-cli lastsave
```

### 实时监控
```bash
redis-cli info stats | grep -E "instantaneous_ops_per_sec|instantaneous_input_kbps"
```

## 排障流程
1. 检查内存使用：`used_memory` 是否接近 `maxmemory`，`mem_fragmentation_ratio` > 1.5 需关注
2. 检查连接数：`connected_clients` 是否异常增长
3. 查看慢日志：找出耗时超过 10ms 的命令
4. 检查 `evicted_keys`：有驱逐说明内存不足，需调整 maxmemory 或 eviction policy
5. 检查持久化：RDB/AOF 是否正常，`rdb_last_bgsave_status` 是否为 ok
6. 检查 `rejected_connections`：非零说明达到 maxclients 限制
