# Prometheus 告警后自动 AI 诊断+修复，想听听大家的痛点

## 背景

我在做一个开源运维工具 **NightMend**，核心功能是：

**Prometheus AlertManager 告警触发后，AI 自动诊断根因并执行修复。**

不替换 Prometheus，只做"告警之后"的事。你只需要在 AlertManager 加一行 webhook 配置。

## 它解决什么问题？

你现在的工作流大概是这样的：

```
Prometheus 告警响了
    → 打开 Grafana 看图表
    → SSH 到服务器
    → top / df -h / docker ps / journalctl ...
    → 找到原因
    → 手动修复（重启服务、清理磁盘、kill 进程...）
    → 确认恢复
```

这中间的 **10-30 分钟**，就是 NightMend 要自动化的部分。

## 它怎么工作？

```
Prometheus → AlertManager → webhook → NightMend
                                        │
                                   AI 自动诊断根因
                                        │
                                   匹配修复 Runbook
                                        │
                              ┌─────────┼─────────┐
                              ▼         ▼         ▼
                          自动修复    人工审批    仅通知
                         (低风险)   (高风险)   (只给建议)
```

### 首发支持 5 个场景

| 告警 | AI 诊断 | 自动修复 |
|------|---------|----------|
| CPU 飙高 | top 分析 + 进程排序 | 识别异常进程，可选 kill |
| 磁盘满 | du 分析 + 大文件/日志定位 | 清理日志/临时文件 |
| 服务挂了 | systemctl status + journalctl | 重启服务/容器 |
| 内存不足 | free + ps 分析 | 识别内存泄漏进程 |
| 容器崩溃 | docker logs + inspect | 重启容器 |

### 安全设计

- 所有命令通过白名单校验，禁止危险操作（rm -rf、DROP TABLE 等）
- 高风险操作需要人工审批
- AI 给出"修复信心分数"，只有信心 > 90% 才自动执行
- 完整的审计日志

## 想问几个问题

**真心想了解大家的工作流，不是打广告：**

1. 你们每次收到 Prometheus 告警后，**平均花多长时间**排查+修复？
2. **最常见的 5 个告警**是什么？（CPU 高？磁盘满？服务挂了？OOM？网络不通？）
3. 如果有个工具能在告警后 **30 秒自动诊断**并给你修复方案（甚至一键执行），你愿意试吗？
4. 你管**多少台服务器**？用什么告警通知渠道（钉钉/飞书/Slack/邮件）？
5. 你现在用什么做自动化运维？Ansible？自己写脚本？还是纯手动？

## 技术栈

- **后端：** FastAPI + PostgreSQL + Redis
- **AI：** 支持 OpenAI / Claude / 本地模型
- **Agent：** Python 客户端，支持 Linux / Windows
- **前端：** React + Ant Design

## 开源地址

**GitHub:** [LinChuang2008/nightmend](https://github.com/LinChuang2008/nightmend)

如果你有兴趣试用，欢迎留言或私信我。我们可以一起调试你的告警场景。

---

*NightMend — Prometheus 负责监控，NightMend 负责修。*
