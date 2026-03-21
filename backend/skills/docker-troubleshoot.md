---
name: docker-troubleshoot
description: Docker 容器运行异常排查
triggers:
  - docker
  - 容器
  - container
  - compose
  - 镜像
  - image
  - exit
  - restart
---

# Docker 排障技能

## 适用场景
容器频繁重启、OOMKilled、网络不通、磁盘空间不足、镜像拉取失败等问题。

## 常用诊断命令

### 查看容器状态
```bash
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"
```

### 查看容器日志
```bash
# 替换 <container> 为实际容器名
docker logs --tail 100 <container>
docker logs --tail 100 --timestamps <container> 2>&1 | grep -iE "error|fatal|panic|oom"
```

### 查看容器详情
```bash
docker inspect <container> | python3 -m json.tool | grep -A5 -E "State|OOMKilled|ExitCode|RestartCount"
docker inspect <container> --format '{{.State.OOMKilled}} {{.State.ExitCode}} {{.RestartCount}}'
```

### 磁盘空间
```bash
docker system df
docker images --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}" | sort -k3 -h | tail -20
```

### 网络诊断
```bash
docker network ls
docker network inspect bridge | python3 -m json.tool | grep -E "Name|Subnet|Gateway"
```

### Docker Compose
```bash
docker compose ps 2>/dev/null || docker-compose ps
docker compose logs --tail 50 2>/dev/null || docker-compose logs --tail 50
```

## 排障流程
1. `docker ps -a` 查看所有容器状态，找出 Exited 或频繁重启的容器
2. `docker inspect` 检查 `OOMKilled`（内存不足被杀）和 `ExitCode`
3. `docker logs` 查看容器内部错误日志
4. `docker stats` 查看资源使用，判断是否需要调整 memory limit
5. `docker system df` 检查磁盘空间，必要时执行 `docker system prune`
6. 网络问题：检查容器 IP、端口映射、防火墙规则
