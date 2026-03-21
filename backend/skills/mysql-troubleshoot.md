---
name: mysql-troubleshoot
description: MySQL 性能与连接问题排查
triggers:
  - mysql
  - 数据库连接
  - slow query
  - 慢查询
  - innodb
  - 连接数
  - too many connections
---

# MySQL 排障技能

## 适用场景
MySQL 连接数异常、慢查询、主从延迟、锁等待、OOM 等问题。

## 常用诊断命令

### 查看连接状态
```bash
mysql -e "SHOW STATUS LIKE 'Threads_connected';"
mysql -e "SHOW STATUS LIKE 'Max_used_connections';"
mysql -e "SHOW VARIABLES LIKE 'max_connections';"
mysql -e "SHOW FULL PROCESSLIST;"
```

### 查看慢查询
```bash
mysql -e "SHOW VARIABLES LIKE 'slow_query_log%';"
mysql -e "SHOW VARIABLES LIKE 'long_query_time';"
tail -100 /var/log/mysql/slow.log 2>/dev/null || tail -100 /var/lib/mysql/*-slow.log 2>/dev/null
```

### InnoDB 状态
```bash
mysql -e "SHOW ENGINE INNODB STATUS\G" | head -100
mysql -e "SELECT * FROM information_schema.INNODB_TRX\G"
mysql -e "SELECT * FROM information_schema.INNODB_LOCKS\G"
```

### 查看数据库大小
```bash
mysql -e "SELECT table_schema, ROUND(SUM(data_length+index_length)/1024/1024,2) AS 'Size(MB)' FROM information_schema.tables GROUP BY table_schema;"
```

## 排障流程
1. 检查连接数是否接近 max_connections（超过 80% 需警惕）
2. 查看 PROCESSLIST 中是否有长时间运行的查询（State = "Locked" 或 "Waiting"）
3. 检查慢查询日志，找出耗时 SQL
4. 分析 InnoDB 状态，查看是否有锁等待或死锁
5. 检查内存使用：`innodb_buffer_pool_size` 是否合理（建议为物理内存的 70%）
