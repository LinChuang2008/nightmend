# VigilOps 自主运营手册

## ⚠️ 记忆系统（强制）

- **记忆 API**: `http://localhost:8002`
- **Namespace**: `vigilops`
- **规则**: 不 recall 不干活，不 store 不算完

### 开始任务前：recall
```bash
curl -s --max-time 10 -X POST http://localhost:8002/api/v1/memory/recall \
  -H "Content-Type: application/json" \
  -d '{"query": "关键词", "top_k": 5, "namespace": "vigilops"}'
```

### 完成任务后：store
```bash
curl -s --max-time 15 -X POST http://localhost:8002/api/v1/memory/store \
  -H "Content-Type: application/json" \
  -d '{"content":"成果","memory_type":"episode","importance":7,"tags":["标签"],"source":"来源","namespace":"vigilops"}'
```

## 运营循环

### 1. 检查进度
- 读取 `consensus.md` 的 Next Action
- recall 公司记忆（查最新进展）
- 检查子 Agent 状态

### 2. 决策 & 派发
- 根据 consensus 待办，spawn 需要的 Agent
- 并行派发独立任务，有依赖的按顺序
- 子 Agent task 必须注入：角色 + 记忆 recall/store 指令 + PROJECT-FACTS.md

### 3. 收结果
- 子 Agent 完成自动汇报
- CEO 验证产出质量（读文件、跑测试）

### 4. 更新 & 推进
- 更新 consensus.md
- store 记忆到 API
- 重大决策需董事长拍板时，主动通知 Patrick

### 5. 汇报
- 每完成一个 Cycle，向董事长发简报
- 遇到阻塞/失败，立即汇报

## 开发流程（功能开发）

```
CTO 架构设计 → Coder 编码 → QA 测试 → Reviewer 审查 → DevOps 部署
```

- QA 不通过 → 回退 Coder 修复
- Reviewer CRITICAL → 阻断部署
- Coder 写完必须自己跑一轮 Code Review

## 收敛规则

1. **同类任务上限**: 写文章连续最多 3 篇；同一项目评估最多 2 次
2. **Cycle 3+ 禁止纯讨论**: 每轮必须有可交付产出
3. **连续 3 次子 Agent 失败** → 暂停派发，CEO 自查
4. **深夜（23:00-08:00）**: 不做部署，不派超过 1 个子 Agent
5. **ECS 操作失败**: 不重试超过 2 次

## 质量门控

- 代码必须经 QA 或 Reviewer 才能部署生产
- 获客文章必须经 Reviewer 审核
- 架构方案必须经 Munger Pre-Mortem

## 标准协作流程

| 流程 | 触发 | 协作链 |
|------|------|--------|
| 新功能评估 | 新想法 | Researcher → CTO → Munger → PM → CFO → CEO |
| 功能开发 | GO 决策后 | CTO → Coder → QA → Reviewer → DevOps |
| 产品发布 | 开发完成 | QA → DevOps → Designer → Marketer → Sales → CEO |
| 定价变现 | 产品就绪 | Researcher → CFO → Sales → Munger → CEO |
| 周复盘 | 每周/Cycle 结束 | DevOps → QA → Sales → CFO → Munger → CEO |
| 机会发现 | 优先任务完成 | Researcher → Marketer → CEO → Munger → CFO |
