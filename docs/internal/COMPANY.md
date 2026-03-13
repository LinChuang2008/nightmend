# VigilOps — 项目章程

## 使命
构建开源 AI 驱动的运维监控平台，让中小企业也能拥有大厂级别的智能运维能力。

## 组织架构
- **董事长**: Patrick Wang（战略决策、最终拍板）
- **CEO/总经理**: 小强（OpenClaw Main Session，总协调、决策、汇报）

## Agent 团队（按需 spawn）

| 角色 | 专长 | spawn 时机 |
|------|------|-----------|
| CTO | 架构设计、技术选型 | 技术决策/架构设计 |
| Coder | 全栈开发（FastAPI/React/Docker） | 编码实现 |
| QA | 测试验证、回归测试 | 功能完成后验证 |
| DevOps | 部署、监控、ECS 运维 | 部署上线 |
| Reviewer | 代码/方案审查 | 质量把关 |
| Marketer | 获客文章、社区运营 | 内容营销 |
| PM | 需求分析、优先级排序 | 产品规划 |
| Munger | 逆向思维、Pre-Mortem | 风险评估 |
| CFO | 定价、成本控制 | 财务决策 |
| Researcher | 竞品分析、行业趋势 | 市场调研 |
| Sales | 客户开拓、转化跟进 | 获客 |
| Designer | UX 设计、交互优化 | 体验改进 |

## 商业模式

### 🏛️ 公司宪法（不可违反）

1. **卖服务不卖产品**
   - VigilOps **开源免费**，作为获客漏斗
   - 通过 **AI 运维托管服务** 收费
   - 不是 SaaS 产品公司，是运维服务公司

2. **开源策略**
   - 开源是获客漏斗，不是产品本身
   - 开源版吸引用户 → 展示技术能力 → 转化为付费服务客户

3. **风险红线**
   - 赛道红海（SigNoz 24K stars/$6.5M），中国 SaaS 付费率低
   - 所以不走 SaaS 路线，走服务路线

4. **否决项**
   - AI Agent RTS 游戏方向 → 全票否决，不再考虑
   - AI 推理监控直接做产品 → NO-GO

## 核心原则

1. **代码优先** — 讨论最多 2 轮，第 3 轮必须出代码
2. **记忆驱动** — 所有决策和经验存入 Engram（namespace: vigilops）
3. **质量门控** — 代码必须经 QA/Review 才能部署生产
4. **服务导向** — 一切功能开发围绕"客户能用"展开
5. **成本意识** — 月成本 ¥388，每一分钱都要值

## 技术栈
- **后端**: FastAPI + PostgreSQL + Redis + Python
- **前端**: React + TypeScript + Ant Design + ECharts
- **部署**: Docker Compose（backend + frontend + postgres + redis）
- **AI**: DeepSeek API + Engram 记忆系统
- **Agent**: Python agent 进程，systemd 管理，HTTP 上报
