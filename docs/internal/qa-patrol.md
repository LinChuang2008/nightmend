# QA Patrol Report

## 巡检时间
2026-02-28 04:00 CST

## 最近代码变更
c5e0fc9~5107a52: UI菜单修复、响应式布局、agent Decimal序列化修复、手动IP配置、Redis rate limiting清理

## API 测试结果

| API | 状态 | 结果 |
|-----|------|------|
| POST /api/auth/login | 502 | ❌ Bad Gateway |
| GET /api/services | 502 | ❌ Bad Gateway |
| GET /api/alerts | 502 | ❌ Bad Gateway |

## 🐛 P0: Demo后端宕机
- 环境: http://139.196.210.68:3001
- Nginx返回502，upstream不可达
- 影响: 整站不可用
- 建议: 检查ECS Docker容器，重启后端

## Engram回忆
- 历史P0: 告警引擎不评估service规则
- 测试覆盖率<5%

## 总结
Demo环境完全不可用，P0事故。需DevOps优先恢复。
