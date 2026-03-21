---
name: linux-performance
description: Linux 系统性能分析（CPU、内存、磁盘、网络）
triggers:
  - cpu
  - 内存
  - 磁盘
  - load average
  - 负载
  - iowait
  - 性能
  - 卡顿
  - 响应慢
  - oom killer
---

# Linux 性能排障技能

## 适用场景
CPU 高负载、内存不足、磁盘 I/O 瓶颈、网络延迟、系统响应慢等问题。

## 常用诊断命令

### CPU 分析
```bash
top -bn1 | head -20
mpstat -P ALL 1 3 2>/dev/null || vmstat 1 5
ps aux --sort=-%cpu | head -15
cat /proc/loadavg
```

### 内存分析
```bash
free -h
cat /proc/meminfo | grep -E "MemTotal|MemFree|MemAvailable|Buffers|Cached|SwapUsed"
ps aux --sort=-%mem | head -15
dmesg | grep -i "oom" | tail -20
```

### 磁盘 I/O 分析
```bash
df -h
iostat -x 1 3 2>/dev/null || cat /proc/diskstats | head -20
iotop -bn 3 2>/dev/null | head -20
lsof +D / 2>/dev/null | wc -l
```

### 网络分析
```bash
ss -s
netstat -an | awk '{print $6}' | sort | uniq -c | sort -rn | head -10
ip -s link show
cat /proc/net/dev | column -t
```

### 系统日志
```bash
dmesg | tail -50
journalctl -p err -n 50 --no-pager 2>/dev/null || tail -100 /var/log/syslog
```

## 排障流程
1. **CPU**：load average > CPU 核心数 × 2 时需关注；`iowait` 高说明磁盘是瓶颈
2. **内存**：`MemAvailable` < 总内存 10% 时危险；检查 OOM Killer 日志
3. **磁盘**：`df -h` 查看使用率；`iostat` 查看 `%util` 是否接近 100%
4. **网络**：检查 TIME_WAIT 连接数是否过多；检查网卡错误包数
5. 综合分析：结合 `top` 找出资源消耗最高的进程，针对性处理
