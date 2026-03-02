# Service 告警规则评估修复报告

**日期**: 2026-03-02  
**修复人**: DHH (VigilOps 全栈工程师)  
**严重级别**: P0  
**状态**: ✅ 已修复并验证

---

## Bug 描述

Service 类告警规则（`target_type = "service"`，如 nginx down）不被 alert_engine 评估。只有 host 类指标告警在跑，所有服务级别告警永远不触发。

## 根因分析

原始 `alert_engine_loop()` 只调用 `evaluate_host_rules()`，`evaluate_service_rules()` 函数存在但从未被接入主循环。

## 修复内容

**Commit**: `26ba096` — fix: async/sync混用 + Redis bytes保护 in alert_engine.py  
**时间**: 2026-03-02 00:37:15 +0800 | **分支**: main

### 核心变更（alert_engine.py）
1. 新增 `evaluate_service_rules()` — 查询所有 `target_type=service` 的已启用规则，逐服务评估
2. 新增 `_evaluate_service_rule()` — 支持 `service_down` 指标、持续时间检查、告警去重、创建 Alert 记录、发布 Redis 事件
3. `alert_engine_loop()` 接入调用：`await evaluate_service_rules()`
4. async/sync 混用修复：`run_in_executor` 包装同步 DB dedup 调用
5. Redis bytes 解码保护：`first_seen.decode('utf-8')` 防止类型错误

## 验证结果

插入 `status=down` 测试服务 `nginx-test`，等待 60s 评估周期：

```
2026-03-02 03:55:51 INFO alert_engine: Service alert will be created: 服务不可用 - nginx-test
2026-03-02 03:55:51 INFO alert_engine: Service alert fired: 服务不可用 - nginx-test
2026-03-02 03:55:51 INFO remediation.listener: Received alert event: alert_id=2
```

✅ service 类规则成功评估  
✅ Alert 记录成功写入 alerts 表（service_id 字段正确关联）  
✅ Redis 事件发布正常，remediation listener 收到  
✅ 告警引擎无崩溃，持续运行

## Commit ID

`26ba096`
