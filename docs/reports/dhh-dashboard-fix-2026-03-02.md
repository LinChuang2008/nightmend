# DHH Dashboard Fix Report

> 修复日期：2026-03-02  
> 工程师：DHH (VigilOps 全栈工程师)  
> Commit ID：ea8a113  

---

## 修复总结

| 问题 | 优先级 | 状态 | 修复方式 |
|------|--------|------|---------|
| 右侧趋势图溢出截断 | P0-1 | ✅ 已修复 | ResizeObserver 精确测量容器宽度 |
| Dashboard i18n 不完整 | P0-2 | ✅ 已修复 | 全组件硬编码中文替换为 t() |
| 趋势图高度太矮(80px) | P1-1 | ✅ 已修复 | 高度提升到 200px |
| 健康评分频繁跳动 | P1-2 | ✅ 已修复 | 800ms debounce 防抖 |

---

## P0-1：右侧趋势图溢出截断 ✅

### 问题原因
`CustomizableDashboard.tsx` 中使用 `window.innerWidth - 32` 计算容器宽度，未减去侧边栏宽度（~220px），导致 `ResponsiveGridLayout` 宽度超出实际内容区，右侧图表被截断。

### 修复方案
- 在外层 `<div>` 添加 `ref={containerRef}` 和 `overflow: hidden`
- 使用 `ResizeObserver` 监听容器实际宽度变化，准确获取可用宽度
- 移除 `window.addEventListener('resize', ...)` 改为 DOM 层面精确测量

```tsx
// 修复前
const updateWidth = () => {
  const width = window.innerWidth - 32; // ❌ 未考虑侧边栏
  setContainerWidth(Math.max(320, width));
};

// 修复后
const observer = new ResizeObserver((entries) => {
  const width = entries[0]?.contentRect.width;
  if (width) setContainerWidth(Math.max(320, width)); // ✅ 测量实际容器
});
observer.observe(containerRef.current);
```

---

## P0-2：Dashboard i18n 不完整 ✅

### 问题原因
Dashboard 所有子组件中存在大量硬编码中文字符串，切换到 EN 后无法翻译。

### 修复文件
- `CustomizableDashboard.tsx` - 标题、按钮、消息、状态文字
- `MetricsCards.tsx` - 服务器/服务/数据库/告警/健康评分标签
- `TrendCharts.tsx` - 图表标题 (CPU趋势/内存趋势/告警趋势/错误日志)
- `AlertsList.tsx` - 表格列标题/空状态
- `ServersOverview.tsx` - 卡片标题/空状态
- `LogStats.tsx` - 标题/统计标签
- `ResourceCharts.tsx` - 资源对比/网络带宽图表

### 新增翻译键（en.ts / zh.ts 各增加 ~35 键）
```
dashboard.systemOverview / 系统概览
dashboard.realtime / 实时
dashboard.polling / 轮询
dashboard.editMode / 编辑模式
dashboard.lockLayout / 锁定布局
dashboard.unlockLayout / 解锁编辑
dashboard.exportData / 导出数据
dashboard.servers / 服务器
dashboard.services / 服务
dashboard.databases / 数据库
dashboard.activeAlerts / 活跃告警
dashboard.online / 在线
dashboard.offline / 离线
dashboard.healthy / 健康
dashboard.unhealthy / 异常
dashboard.recentAlertsTitle / 最新告警
dashboard.alertTitle / 标题
dashboard.alertSeverity / 严重级别
dashboard.alertFiredAt / 触发时间
dashboard.noActiveAlerts / 暂无活跃告警
dashboard.logStatTitle / 最近 1 小时日志统计
dashboard.logTotal / 日志总量
dashboard.noData / 暂无数据
dashboard.noMetrics / 暂无指标数据
dashboard.serverHealthOverview / 服务器健康总览
dashboard.cpuTrend / CPU 趋势 (24h)
dashboard.memTrend / 内存趋势 (24h)
dashboard.alertTrend / 告警趋势 (24h)
dashboard.errorLogTrend / 错误日志 (24h)
dashboard.loadingDashboard / 正在加载仪表盘...
dashboard.networkBandwidth / 网络带宽 (KB/s)
dashboard.resourceUsage / 资源使用率对比
```

### 截图验证
- 切换 EN 后：`System Overview • Realtime | Dashboard Settings | Export Data`
- MetricsCards：`Servers | Services | Databases | Active Alerts`
- TrendCharts：`CPU Trend (24h) | Memory Trend (24h) | Alert Trend (24h)`
- ResourceCharts：`Resource Usage | Network (KB/s)` + 图例 `Memory Usage | Disk Usage | Upload | Download`
- LogStats：`Log Statistics (1h) | Total Logs`
- AlertsList：`Latest Alerts | Title | Severity | Fired At`

---

## P1-1：趋势图高度太矮 ✅

### 问题原因
`TrendCharts.tsx` 中 `<ReactECharts style={{ height: 80 }}` 高度仅 80px，图表数据不可读。

### 修复方案
```tsx
// 修复前
<ReactECharts option={sparklineOption(...)} style={{ height: 80 }} />

// 修复后
<ReactECharts option={sparklineOption(...)} style={{ height: 200 }} />
```
同步调整 `grid` 内边距：`{ top: 30, bottom: 10, left: 10, right: 10 }`，确保标题和内容都有足够空间。

---

## P1-2：健康评分频繁跳动 ✅

### 问题原因
WebSocket `wsData.health_score` 每次推送都直接更新 UI，短时间内评分多次变化（4→3→2）。

### 修复方案
添加 800ms debounce，只有评分稳定 800ms 后才更新显示：

```tsx
// 新增 debouncedHealthScore 状态
const [debouncedHealthScore, setDebouncedHealthScore] = useState<number>(100);
const healthScoreTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

// debounce effect
useEffect(() => {
  const rawScore = wsData?.health_score ?? 100;
  if (healthScoreTimerRef.current) clearTimeout(healthScoreTimerRef.current);
  healthScoreTimerRef.current = setTimeout(() => {
    setDebouncedHealthScore(rawScore); // 800ms 后才更新
  }, 800);
}, [wsData?.health_score]);

// MetricsCards 使用 debouncedHealthScore 而非直接用 wsData.health_score
const healthScore = debouncedHealthScore;
```

---

## 部署记录

### 本地容器
```bash
cd frontend && npx vite build
docker cp dist/. vigilops-frontend-1:/usr/share/nginx/html/
```
✅ 本地 http://localhost:3001 验证通过

### ECS 部署（139.196.210.68:3001）
```bash
tar czf /tmp/vigilops-dist.tar.gz dist/
scp /tmp/vigilops-dist.tar.gz root@139.196.210.68:/tmp/
ssh root@139.196.210.68 'cd /tmp && tar xzf vigilops-dist.tar.gz && docker cp dist/. vigilops-frontend-1:/usr/share/nginx/html/'
```
✅ ECS http://139.196.210.68:3001 验证通过

### Git
```
commit ea8a113 (HEAD -> main)
fix(dashboard): 补充 ResourceCharts i18n 翻译

commit 4d7a79f
fix(dashboard): 修复4个样式/功能问题
```

---

## 截图证据

| 截图 | 验证点 |
|------|--------|
| `/Users/patrick_wang/.openclaw/media/browser/09910067-982f-4e5c-8e08-7fe026ea85fa.jpg` | 本地 EN 语言：No Monitoring Data / Add Host (i18n 验证) |
| `/Users/patrick_wang/.openclaw/media/browser/ac416750-8319-4a0a-bd4e-1e030561edfe.jpg` | ECS Loading dashboard... (i18n 验证) |
| `/Users/patrick_wang/.openclaw/media/browser/2d7ff411-2196-49a9-96a1-ffcd2ced8c0d.jpg` | ECS Dashboard 第一次加载 - System Overview / Realtime |
| `/Users/patrick_wang/.openclaw/media/browser/a93fce42-aa75-48e2-b376-e97a907478ce.jpg` | ECS 最终全页（强刷后）- 所有翻译 + 趋势图高度 + 资源图英文 |

---

> 报告由 DHH (VigilOps 全栈工程师) 生成  
> 2026-03-02 GMT+8
