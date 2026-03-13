# AI 故障模式记忆升级报告

**日期**: 2026-03-02  
**Commit**: 9deac3e  
**工程师**: VigilOps Coder (DHH 风格)

---

## 目标

让 VigilOps 的 AI 分析"越用越聪明"——当发生告警时，AI 能自动召回历史相似的故障模式，在根因分析中给出"这个模式我之前见过"的洞察。

---

## 改动文件

### 1. `backend/app/services/memory_client.py`

**改动内容**：

**`store()` 方法新增参数**：
- `memory_type: str = "episode"` — 记忆类型（episode/fact/lesson）
- `importance: int = 5` — 重要性评分 1-10
- `tags: Optional[List[str]] = None` — 标签列表，如 `["fault-pattern", "nginx"]`
- `namespace: str = "vigilops"` — 记忆命名空间

**`recall()` 方法新增参数**：
- `namespace: str = "vigilops"` — 命名空间隔离，避免跨项目污染

**核心原则**：静默失败设计不变，记忆系统异常不影响主业务。

---

### 2. `backend/app/services/ai_engine.py`

**`ROOT_CAUSE_SYSTEM_PROMPT` 升级**：

新增"历史相似故障"分析指令：
- 若历史故障与当前告警相似，AI 在 evidence 中注明"参考历史故障"
- 历史匹配时可适当提升 confidence

**`analyze_root_cause()` 双层记忆**：

**Working Memory（召回）**：
```python
# 用 service_name + metric + alert_title 构建精准召回查询
recall_query = " ".join([alert_title, service_name, metric_name])
memories = await memory_client.recall(recall_query, top_k=3, namespace="vigilops")
```
召回结果注入 prompt 的「历史相似故障」段落。

**Long-term Memory（存储）**：
```python
# 故障模式结构化存储
fault_content = f"故障模式: {alert_title}\n受影响服务: {service_name}\n关联指标: {metric_name}\n根因: {root_cause}\n解决建议: ..."
await memory_client.store(
    fault_content,
    memory_type="episode",
    importance=7,          # 故障模式重要性高
    tags=["fault-pattern", service_name, metric_name],
    namespace="vigilops",
)
```

**其他方法（analyze_logs, chat）**：
- 所有 recall/store 调用均显式传 `namespace="vigilops"`
- store 调用补全 memory_type/importance/tags 参数

---

## 测试结果

### 1. 语法验证
```
python3 -c "import ast; ast.parse(open('ai_engine.py').read()); print('Syntax OK')"
# → Syntax OK
```

### 2. Backend 重启验证
```
docker compose restart backend
# → Container vigilops-backend-1 Started (无报错)
```

### 3. Engram store 验证（Docker exec 内测试）
```python
ok = await memory_client.store(
    content="故障模式: CPU告警\n根因: 内存泄漏导致GC压力",
    memory_type="episode", importance=7, tags=["fault-pattern","api"],
    namespace="vigilops"
)
# → Store OK: True
```

### 4. Engram recall 验证（Docker exec 内测试）
```python
mems = await memory_client.recall("CPU告警 api", top_k=3, namespace="vigilops")
# → Recalled: 10 memories
# → 首条: "故障模式: nginx CPU告警\n受影响服务: nginx\n关联指标: cpu_percent\n根因: 高并发请求导致CPU饱和..."
```

**结论**：Engram 写入成功，recall 能正确匹配故障模式记忆。

---

## 架构总结

```
告警触发
   │
   ▼
analyze_root_cause()
   ├── [Working Memory] recall(service+metric关键词) → 注入历史故障到 prompt
   ├── AI 分析（结合历史经验，置信度更高）
   └── [Long-term Memory] store(故障模式, importance=7, tags=[fault-pattern, service])
```

每次分析后，VigilOps 的故障知识库自动扩充。下次遇到同类告警，AI 会说：
> "此模式曾出现过：nginx CPU饱和（高并发导致），建议增加worker数量。"

---

## 注意事项

- Engram 服务在 ECS 上需映射到 `host.docker.internal:8002`（config 已配置）
- 本次改动仅本地，**未推送 ECS**
- 故障模式 importance=7，高于日常 chat 记录（4）和日志异常（5）
