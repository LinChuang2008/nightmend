---
name: nginx-troubleshoot
description: Nginx 访问异常与配置问题排查
triggers:
  - nginx
  - 502
  - 504
  - upstream
  - 反向代理
  - 访问日志
  - access log
---

# Nginx 排障技能

## 适用场景
Nginx 502/504 错误、upstream 连接失败、配置错误、性能瓶颈等问题。

## 常用诊断命令

### 查看 Nginx 状态
```bash
systemctl status nginx
nginx -t
nginx -V 2>&1 | head -5
```

### 查看错误日志
```bash
tail -100 /var/log/nginx/error.log
tail -100 /var/log/nginx/access.log | awk '{print $9}' | sort | uniq -c | sort -rn | head -20
```

### 查看连接状态
```bash
curl -s http://localhost/nginx_status 2>/dev/null || echo "stub_status not enabled"
ss -tnp | grep nginx | wc -l
netstat -an | grep :80 | grep ESTABLISHED | wc -l
```

### 查看 upstream 状态
```bash
grep -r "upstream" /etc/nginx/conf.d/ /etc/nginx/sites-enabled/ 2>/dev/null
```

### 查看 worker 进程
```bash
ps aux | grep nginx
cat /proc/$(cat /var/run/nginx.pid 2>/dev/null)/limits 2>/dev/null | grep "open files"
```

## 排障流程
1. 检查 Nginx 进程是否运行，配置文件是否有语法错误（`nginx -t`）
2. 查看 error.log 中的具体错误信息（502 通常是 upstream 问题）
3. 检查 upstream 后端服务是否正常响应
4. 查看 access.log 中的状态码分布，定位异常请求
5. 检查系统文件描述符限制（`ulimit -n`）是否足够
6. 检查 worker_connections 配置是否合理
