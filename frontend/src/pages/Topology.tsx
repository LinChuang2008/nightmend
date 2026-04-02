/**
 * 服务拓扑图页面
 *
 * 图表展示 + 侧面板编辑：
 * - 左侧：ECharts 拓扑图（拖拽节点 + 保存布局）
 * - 右侧面板：依赖关系列表、添加/删除依赖、AI 推荐
 */
import { useEffect, useRef, useState, useCallback } from 'react';
import { useResponsive } from '../hooks/useResponsive';
import {
  Typography, Button, Spin, message, Radio, Space, Tag,
  Drawer, List, Select, Card, Divider, Empty, Popconfirm, Tooltip,
} from 'antd';
import {
  ReloadOutlined, ApartmentOutlined, NodeIndexOutlined,
  EditOutlined, SaveOutlined, UndoOutlined, RobotOutlined,
  PlusOutlined, DeleteOutlined, CheckOutlined, CloseOutlined,
  BulbOutlined, UnorderedListOutlined,
} from '@ant-design/icons';
import * as echarts from 'echarts/core';
import { GraphChart } from 'echarts/charts';
import { TooltipComponent, LegendComponent, GraphicComponent } from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';

echarts.use([GraphChart, TooltipComponent, LegendComponent, GraphicComponent, CanvasRenderer]);
import { useTranslation } from 'react-i18next';
import { EmptyState, ErrorState } from '../components/StateComponents';

const { Title, Text, Paragraph } = Typography;

/* ==================== 类型 ==================== */

interface TopoNode {
  id: number; name: string; type: string; status: string;
  host: string; host_id?: number; group: string;
}
interface TopoEdge {
  source: number; target: number; type: string;
  description: string; id?: number; manual?: boolean;
}
interface TopologyData {
  nodes: TopoNode[]; edges: TopoEdge[];
  saved_positions?: Record<string, { x: number; y: number }> | null;
  has_custom_deps?: boolean;
}
interface AISuggestion {
  source: number; target: number; type: string; description: string;
}

type LayoutMode = 'grouped' | 'force';

/* ==================== 配置 ==================== */

const GROUP_CONFIG: Record<string, { color: string; bgColor: string; order: number; stage: number }> = {
  web:      { color: '#FFB800', bgColor: 'rgba(255,184,0,0.08)',   order: 0, stage: 0 },
  api:      { color: '#FF7F50', bgColor: 'rgba(255,127,80,0.08)',  order: 1, stage: 1 },
  app:      { color: '#4FC3F7', bgColor: 'rgba(79,195,247,0.08)',  order: 2, stage: 1 },
  registry: { color: '#AB47BC', bgColor: 'rgba(171,71,188,0.08)',  order: 3, stage: 2 },
  mq:       { color: '#00CED1', bgColor: 'rgba(0,206,209,0.08)',   order: 4, stage: 2 },
  olap:     { color: '#FF8A65', bgColor: 'rgba(255,138,101,0.08)', order: 5, stage: 2 },
  database: { color: '#7B68EE', bgColor: 'rgba(123,104,238,0.08)', order: 6, stage: 3 },
  cache:    { color: '#9ACD32', bgColor: 'rgba(154,205,50,0.08)',   order: 7, stage: 3 },
};

/** 管道阶段定义（从左到右） —— label 存储 i18n key，在组件内翻译 */
const PIPELINE_STAGES = [
  { key: 0, label: 'topology.stageAccess', color: '#FFB800' },
  { key: 1, label: 'topology.stageApp', color: '#FF7F50' },
  { key: 2, label: 'topology.stageMiddleware', color: '#AB47BC' },
  { key: 3, label: 'topology.stageData', color: '#7B68EE' },
];

const STATUS_COLORS: Record<string, string> = {
  up: '#52c41a', running: '#52c41a', healthy: '#52c41a',
  down: '#ff4d4f', stopped: '#ff4d4f', warning: '#faad14', unknown: '#d9d9d9',
};
const getStatusColor = (s: string) => STATUS_COLORS[s?.toLowerCase()] || STATUS_COLORS.unknown;
const shortName = (name: string) => {
  let s = name.replace(/\s*\(:\d+\)/, '').replace(/-1$/, '');
  return s.length > 18 ? s.substring(0, 16) + '…' : s;
};

const EDGE_STYLES: Record<string, { color: string; type: 'solid' | 'dashed'; width: number; labelKey: string }> = {
  calls:      { color: '#1890ff', type: 'solid',  width: 2,   labelKey: 'topology.legendApiCall' },
  depends_on: { color: '#faad14', type: 'dashed', width: 1.5, labelKey: 'topology.legendDep' },
};

/* ==================== 分组布局 ==================== */

interface StageBox { stageIdx: number; label: string; x: number; y: number; width: number; height: number; color: string; }

/** 计算管道布局位置 (Calculate pipeline layout positions)
 * 按服务分组的阶段布局：接入层→应用层→中间件→数据层，从左到右4个阶段
 * 每个阶段内的节点按纵向排列，实现标准的分层架构可视化
 * @param nodes 拓扑节点数组
 * @param w 画布宽度
 * @param h 画布高度
 * @returns 节点位置映射和阶段框信息
 */
const computePipelinePositions = (nodes: TopoNode[], w: number, h: number) => {
  // 按 stage 分组
  const stageBuckets: TopoNode[][] = [[], [], [], []];
  for (const n of nodes) {
    const cfg = GROUP_CONFIG[n.group];
    const stage = cfg?.stage ?? 1;
    stageBuckets[stage].push(n);
  }

  const stageCount = PIPELINE_STAGES.length;
  const stageWidth = (w - 60) / stageCount;
  const padTop = 70;     // 留给阶段标题
  const padBottom = 30;
  const availH = h - padTop - padBottom;
  const positions = new Map<number, { x: number; y: number }>();
  const stageBoxes: StageBox[] = [];

  stageBuckets.forEach((bucket, si) => {
    const stageCfg = PIPELINE_STAGES[si];
    const stageX = 30 + si * stageWidth;

    stageBoxes.push({
      stageIdx: si,
      label: stageCfg.label,
      x: stageX,
      y: 10,
      width: stageWidth - 10,
      height: h - 20,
      color: stageCfg.color,
    });

    if (bucket.length === 0) return;

    // 节点在阶段内纵向居中排列
    const spacing = Math.min(80, availH / (bucket.length + 1));
    const totalH = spacing * (bucket.length - 1);
    const startY = padTop + (availH - totalH) / 2;
    const centerX = stageX + (stageWidth - 10) / 2;

    bucket.forEach((node, ni) => {
      positions.set(node.id, {
        x: centerX,
        y: startY + ni * spacing,
      });
    });
  });

  return { positions, stageBoxes };
};

/* ==================== 组件 ==================== */

export default function Topology() {
  const { t } = useTranslation();
  const { isMobile } = useResponsive();

  /** 分组类型 → i18n 翻译 */
  const getGroupLabel = (group: string) => {
    const keyMap: Record<string, string> = {
      web:      'topology.categoryWeb',
      api:      'topology.categoryApi',
      app:      'topology.categoryApp',
      registry: 'topology.categoryRegistry',
      mq:       'topology.categoryMq',
      olap:     'topology.categoryOlap',
      database: 'topology.categoryDb',
      cache:    'topology.categoryCache',
    };
    return keyMap[group] ? t(keyMap[group]) : group;
  };
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<echarts.ECharts | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [layout, setLayout] = useState<LayoutMode>('grouped');
  const [stats, setStats] = useState({ nodes: 0, edges: 0 });
  const topoData = useRef<TopologyData | null>(null);

  // 编辑面板
  const [panelOpen, setPanelOpen] = useState(false);
  const [addSource, setAddSource] = useState<number | undefined>();
  const [addTarget, setAddTarget] = useState<number | undefined>();
  const [addType, setAddType] = useState<string>('depends_on');

  // AI 推荐
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSuggestions, setAiSuggestions] = useState<AISuggestion[]>([]);
  const [aiMessage, setAiMessage] = useState('');
  const [aiTab, setAiTab] = useState<'deps' | 'ai'>('deps');

  // 节点名映射
  const nodeNameMap = useRef<Map<number, string>>(new Map());

  /** 获取拓扑图数据 (Fetch topology data)
   * 从后端加载节点、边和已保存的布局位置信息
   * 构建节点名称映射表，用于快速查找和显示
   */
  const fetchData = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await fetch('/api/v1/topology', {
        credentials: 'include',
      });
      if (!res.ok) throw new Error();
      const data: TopologyData = await res.json();
      topoData.current = data;
      setStats({ nodes: data.nodes.length, edges: data.edges.length });
      const nameMap = new Map<number, string>();
      data.nodes.forEach(n => nameMap.set(n.id, n.name));
      nodeNameMap.current = nameMap;
      renderChart(data, layout);
    } catch (err) {
      setLoadError(err);
    } finally { setLoading(false); }
  }, [layout]); // eslint-disable-line

  /** 保存用户自定义布局 (Save custom layout)
   * 读取当前 ECharts 实例中节点的拖拽位置，保存到后端
   * 下次加载时将恢复用户自定义的节点位置
   */
  const saveLayout = async () => {
    const chart = chartInstance.current;
    if (!chart || !topoData.current) return;
    const option = chart.getOption() as any;
    const seriesData = option?.series?.[0]?.data;
    if (!seriesData) return;

    const positions: Record<string, { x: number; y: number }> = {};
    for (const node of seriesData) {
      if (node.x !== undefined && node.y !== undefined) {
        positions[node.id] = { x: node.x, y: node.y };
      }
    }
    try {
      const res = await fetch('/api/v1/topology/layout', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions }),
      });
      if (!res.ok) throw new Error();
      message.success(t('topology.saveLayoutSuccess'));
    } catch { message.error(t('topology.saveLayoutFailed')); }
  };

  /** 重置为默认布局 (Reset to default layout)
   * 删除用户自定义位置，恢复算法生成的默认布局
   * 清理后端存储的位置数据并重新渲染图表
   */
  const resetLayout = async () => {
    try {
      await fetch('/api/v1/topology/layout', { method: 'DELETE', credentials: 'include' });
      message.success(t('topology.resetLayoutSuccess'));
      fetchData();
    } catch { message.error(t('topology.resetLayoutFailed')); }
  };

  /** 手动添加服务依赖 (Manually add service dependency)
   * 支持两种依赖类型：API调用(calls)和依赖关系(depends_on)
   * 验证源服务和目标服务选择，避免自环依赖
   */
  const addDependency = async () => {
    if (!addSource || !addTarget) { message.warning(t('topology.selectSource')); return; }
    if (addSource === addTarget) { message.warning(t('topology.selfLoop')); return; }
    try {
      const res = await fetch('/api/v1/topology/dependencies', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          source_service_id: addSource,
          target_service_id: addTarget,
          dependency_type: addType,
          description: addType === 'calls' ? t('topology.addCallsDesc') : t('topology.addDependsDesc'),
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || t('topology.addFailed'));
      }
      message.success(t('topology.depAdded'));
      setAddSource(undefined);
      setAddTarget(undefined);
      fetchData();
    } catch (e: any) { message.error(e.message || t('topology.addFailed')); }
  };

  /** 删除依赖 */
  const deleteDependency = async (depId: number) => {
    try {
      await fetch(`/api/v1/topology/dependencies/${depId}`, {
        method: 'DELETE', credentials: 'include',
      });
      message.success(t('topology.deleted'));
      fetchData();
    } catch { message.error(t('topology.deleteFailed')); }
  };

  /** 清空依赖 */
  const clearAllDeps = async () => {
    try {
      await fetch('/api/v1/topology/dependencies', {
        method: 'DELETE', credentials: 'include',
      });
      message.success(t('topology.cleared'));
      fetchData();
    } catch { message.error(t('topology.clearFailed')); }
  };

  /** AI 推荐 */
  const requestAISuggest = async () => {
    setAiLoading(true);
    setAiTab('ai');
    try {
      const res = await fetch('/api/v1/topology/ai-suggest', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || t('topology.aiAnalysisFailed'));
      const data = await res.json();
      setAiSuggestions(data.suggestions || []);
      setAiMessage(data.message || '');
    } catch (e: any) { message.error(e.message); }
    finally { setAiLoading(false); }
  };

  /** 应用单条 AI 建议 */
  const applyOneSuggestion = async (s: AISuggestion) => {
    try {
      const res = await fetch('/api/v1/topology/dependencies', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source_service_id: s.source, target_service_id: s.target, dependency_type: s.type, description: s.description }),
      });
      if (!res.ok) throw new Error();
      message.success(t('topology.applied'));
      setAiSuggestions(prev => prev.filter(x => !(x.source === s.source && x.target === s.target)));
      fetchData();
    } catch { message.error(t('topology.applyFailed')); }
  };

  /** 应用全部 AI 建议 */
  const applyAllSuggestions = async () => {
    const body = aiSuggestions.map(s => ({
      source_service_id: s.source, target_service_id: s.target, dependency_type: s.type, description: s.description,
    }));
    try {
      const res = await fetch('/api/v1/topology/ai-suggest/apply', {
        method: 'POST',
        credentials: 'include',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      message.success(t('topology.batchApplied', { count: data.created }));
      setAiSuggestions([]);
      fetchData();
    } catch { message.error(t('topology.batchApplyFailed')); }
  };

  /** 渲染图表 */
  const renderChart = (data: TopologyData, mode: LayoutMode) => {
    if (!chartRef.current) return;
    if (!chartInstance.current) {
      const savedTheme = localStorage.getItem('nightmend_theme');
      chartInstance.current = echarts.init(chartRef.current, savedTheme === 'dark' ? 'dark' : undefined);
    }
    const chart = chartInstance.current;
    const cw = chartRef.current.clientWidth || 1200;
    const ch = chartRef.current.clientHeight || 800;

    const idMap = new Map<number, string>();
    data.nodes.forEach(n => idMap.set(n.id, n.name));

    const isPipeline = mode === 'grouped';
    const autoLayout = isPipeline ? computePipelinePositions(data.nodes, cw, ch) : null;
    const savedPos = data.saved_positions;

    const categoryNames = Array.from(new Set(data.nodes.map(n => n.group)));
    const categories = categoryNames.map(g => ({
      name: getGroupLabel(g), itemStyle: { color: GROUP_CONFIG[g]?.color || '#999' },
    }));

    const nodes = data.nodes.map(n => {
      const cfg = GROUP_CONFIG[n.group] || { color: '#999' };
      const sp = savedPos?.[String(n.id)];
      const ap = autoLayout?.positions.get(n.id);
      const pos = sp || ap;
      return {
        id: String(n.id), name: shortName(n.name), symbolSize: 40, symbol: 'circle',
        ...(pos ? { x: pos.x, y: pos.y, fixed: isPipeline } : {}),
        itemStyle: { color: cfg.color, borderColor: getStatusColor(n.status), borderWidth: 3, shadowColor: 'rgba(0,0,0,0.1)', shadowBlur: 8 },
        label: { show: true, position: 'bottom' as const, fontSize: 11, color: '#555' },
        tooltip: {
          formatter: `<div style="font-weight:600;margin-bottom:4px">${n.name}</div>` +
            `<div>${t('common.type')}: ${getGroupLabel(n.group)}</div>` +
            `<div>${t('common.status')}: <span style="color:${getStatusColor(n.status)}">●</span> ${n.status}</div>` +
            `<div>${t('databases.host')}: ${n.host || '—'}</div>`,
        },
        category: categoryNames.indexOf(n.group),
      };
    });

    const edges = data.edges.map(e => {
      const style = EDGE_STYLES[e.type] || EDGE_STYLES.depends_on;
      return {
        source: String(e.source), target: String(e.target),
        lineStyle: { color: style.color, type: style.type, width: style.width, curveness: 0.2 },
        edgeSymbol: ['none', 'arrow'] as [string, string], edgeSymbolSize: [0, 8],
        tooltip: {
          formatter: `<b>${idMap.get(e.source) ?? e.source}</b> → <b>${idMap.get(e.target) ?? e.target}</b><br/>${t(style.labelKey)}: ${e.description}`,
        },
      };
    });

    const graphics: any[] = [];
    if (isPipeline && autoLayout?.stageBoxes) {
      const stageBoxes = autoLayout.stageBoxes;
      stageBoxes.forEach((box, i) => {
        // 阶段背景（交替色）
        graphics.push({
          type: 'rect', left: box.x, top: box.y, z: -2, silent: true,
          shape: { width: box.width, height: box.height, r: 6 },
          style: { fill: i % 2 === 0 ? 'rgba(0,0,0,0.02)' : 'rgba(0,0,0,0.04)', stroke: 'none' },
        });
        // 阶段标题
        graphics.push({
          type: 'text', left: box.x + box.width / 2, top: 18, z: 0, silent: true,
          style: {
            text: t(box.label), fontSize: 15, fontWeight: 'bold' as const,
            fill: box.color, textAlign: 'center' as const,
          },
        });
        // 阶段顶部色条
        graphics.push({
          type: 'rect', left: box.x + 10, top: 42, z: 0, silent: true,
          shape: { width: box.width - 20, height: 3, r: 2 },
          style: { fill: box.color },
        });
        // 阶段之间的箭头（除最后一个）
        if (i < stageBoxes.length - 1) {
          const arrowX = box.x + box.width;
          const arrowY = box.height / 2;
          graphics.push({
            type: 'text', left: arrowX - 5, top: arrowY - 8, z: 1, silent: true,
            style: { text: '▸', fontSize: 20, fill: '#ccc' },
          });
        }
      });
    }

    chart.setOption({
      tooltip: { trigger: 'item', confine: true },
      legend: { data: categories.map(c => c.name), orient: 'horizontal', bottom: 10, textStyle: { fontSize: 12 }, itemWidth: 14, itemHeight: 14 },
      graphic: graphics,
      animationDuration: 500,
      series: [{
        type: 'graph', layout: isPipeline ? 'none' : 'force', roam: true, draggable: true, zoom: 1,
        categories, data: nodes, links: edges as any,
        ...(mode === 'force' ? { 
          force: { 
            repulsion: [500, 800],          // 增强节点排斥力，减少重叠
            edgeLength: [180, 350],         // 增加边长范围，减少交叉
            gravity: 0.06,                  // 降低重力，让布局更松散
            layoutAnimation: true,
            friction: 0.7,                  // 增加摩擦力，让动画更稳定
            initLayout: 'circular'          // 初始圆形布局，减少交叉
          } 
        } : {}),
        emphasis: { 
          focus: 'adjacency', 
          disabled: false,
          scale: 1.2,                       // 悬停放大效果
          lineStyle: { width: 4, opacity: 0.8 }, 
          itemStyle: { 
            shadowBlur: 20, 
            shadowColor: 'rgba(0,100,255,0.5)',
            borderWidth: 4,
            opacity: 1
          } 
        },
        blur: {                             // 非相邻节点淡化效果
          itemStyle: { opacity: 0.3 },
          lineStyle: { opacity: 0.1 }
        },
        lineStyle: { curveness: 0.3 },     // 增加弯曲度减少视觉冲突
      }],
    }, true);
    chart.resize();
  };

  const handleLayoutChange = (mode: LayoutMode) => {
    setLayout(mode);
    if (topoData.current) renderChart(topoData.current, mode);
  };

  useEffect(() => {
    fetchData();
    const onResize = () => chartInstance.current?.resize();
    window.addEventListener('resize', onResize);
    return () => { window.removeEventListener('resize', onResize); chartInstance.current?.dispose(); };
  }, []); // eslint-disable-line

  /** 节点下拉选项 */
  const nodeOptions = topoData.current?.nodes.map(n => ({
    value: n.id, label: `${shortName(n.name)}  [${getGroupLabel(n.group)}]`,
  })) || [];

  /** 当前依赖列表 */
  const currentEdges = topoData.current?.edges || [];

  return (
    <div>
      {/* 标题栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>{t('topology.serviceTopology')}</Title>
          <Tag color="blue">{stats.nodes} {t('topology.services')}</Tag>
          <Tag color="orange">{stats.edges} {t('topology.dependencies')}</Tag>
          {topoData.current?.has_custom_deps && <Tag color="green">{t('topology.customDeps')}</Tag>}
        </Space>
        <Space>
          <Radio.Group value={layout} onChange={e => handleLayoutChange(e.target.value)}
            optionType="button" buttonStyle="solid" size="small">
            <Radio.Button value="grouped"><ApartmentOutlined /> {t('topology.pipeline')}</Radio.Button>
            <Radio.Button value="force"><NodeIndexOutlined /> {t('topology.force')}</Radio.Button>
          </Radio.Group>
          <Tooltip title={t('topology.saveLayout')}><Button icon={<SaveOutlined />} onClick={saveLayout}>{t('topology.saveLayout')}</Button></Tooltip>
          <Tooltip title={t('topology.resetLayout')}><Button icon={<UndoOutlined />} onClick={resetLayout}>{t('topology.resetLayout')}</Button></Tooltip>
          <Button type="primary" icon={<EditOutlined />} onClick={() => setPanelOpen(true)}>{t('topology.editDeps')}</Button>
          <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>{t('common.refresh')}</Button>
        </Space>
      </div>

      {/* 图例与操作提示 */}
      <div style={{ marginBottom: 12, padding: '8px 12px', background: '#f8f9fa', borderRadius: 6, border: '1px solid #e8e9ea' }}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 16, alignItems: 'center' }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <strong>{t('topology.legendEdgeLabel')}:</strong> <span style={{ color: '#1890ff' }}>━</span> {t('topology.legendApiCall')}　<span style={{ color: '#faad14' }}>╌╌</span> {t('topology.legendDep')}
          </Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            <strong>{t('topology.legendBorderLabel')}:</strong> <span style={{ color: '#52c41a' }}>●</span> {t('topology.legendNormal')}　<span style={{ color: '#ff4d4f' }}>●</span> {t('topology.legendAbnormal')}
          </Text>
          <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('topology.interactionDrag')} | {t('topology.interactionZoom')} | {t('topology.interactionPan')}
            </Text>
            <Text type="secondary" style={{ fontSize: 12 }}>
              {t('topology.interactionHover')}
            </Text>
          </div>
        </div>
      </div>

      {/* 图表 */}
      {loadError ? (
        <ErrorState error={loadError} onRetry={fetchData} fullScreen />
      ) : !loading && stats.nodes === 0 ? (
        <EmptyState scene="topology" />
      ) : (
        <Spin spinning={loading}>
          <div ref={chartRef} style={{
            width: '100%', height: isMobile ? '70vh' : 'calc(100vh - 230px)',
            minHeight: isMobile ? 400 : 550,
            background: '#fafafa', borderRadius: 8, border: '1px solid #f0f0f0',
          }} />
        </Spin>
      )}

      {/* ===== 编辑面板 (Drawer) ===== */}
      <Drawer
        title={t('topology.editDepsTitle')}
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        width={isMobile ? '100%' : 500}
      >
        {/* Tab 切换 */}
        <Radio.Group value={aiTab} onChange={e => setAiTab(e.target.value)} style={{ marginBottom: 16, width: '100%' }}
          optionType="button" buttonStyle="solid">
          <Radio.Button value="deps" style={{ width: '50%', textAlign: 'center' }}>
            <UnorderedListOutlined /> {t('topology.depsManagement')}
          </Radio.Button>
          <Radio.Button value="ai" style={{ width: '50%', textAlign: 'center' }}>
            <RobotOutlined /> {t('topology.aiRecommendation')}
          </Radio.Button>
        </Radio.Group>

        {aiTab === 'deps' ? (
          <>
            {/* 添加依赖 */}
            <Card size="small" title={<><PlusOutlined /> {t('topology.addDep')}</>} style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>{t('topology.sourceService')}</Text>
                  <Select
                    value={addSource} onChange={setAddSource} placeholder={t('topology.sourceService')}
                    style={{ width: '100%' }} showSearch optionFilterProp="label"
                    options={nodeOptions}
                  />
                </div>
                <div style={{ textAlign: 'center', color: '#999' }}>↓</div>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>{t('topology.targetService')}</Text>
                  <Select
                    value={addTarget} onChange={setAddTarget} placeholder={t('topology.targetService')}
                    style={{ width: '100%' }} showSearch optionFilterProp="label"
                    options={nodeOptions}
                  />
                </div>
                <div>
                  <Text type="secondary" style={{ fontSize: 12 }}>{t('topology.depType')}</Text>
                  <Select value={addType} onChange={setAddType} style={{ width: '100%' }}
                    options={[
                      { label: `━ ${t('topology.legendApiCall')} (calls)`, value: 'calls' },
                      { label: `╌ ${t('topology.legendDep')} (depends_on)`, value: 'depends_on' },
                    ]}
                  />
                </div>
                <Button type="primary" icon={<PlusOutlined />} onClick={addDependency} block>
                  {t('topology.addDepButton')}
                </Button>
              </div>
            </Card>

            <Divider />

            {/* 依赖列表 */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
              <Text strong>{t('topology.currentDeps', { count: currentEdges.length })}</Text>
              {currentEdges.some(e => e.manual) && (
                <Popconfirm title={t('topology.confirmClearDeps')} onConfirm={clearAllDeps} okText={t('common.delete')} okType="danger">
                  <Button size="small" danger icon={<DeleteOutlined />}>{t('topology.clearCustom')}</Button>
                </Popconfirm>
              )}
            </div>

            {currentEdges.length === 0 ? (
              <Empty description={t('topology.noDeps')} />
            ) : (
              <List
                size="small"
                dataSource={currentEdges}
                renderItem={(edge) => (
                  <List.Item
                    actions={edge.manual && edge.id ? [
                      <Popconfirm key="del" title={t('topology.confirmClearDeps')} onConfirm={() => deleteDependency(edge.id!)} okText={t('common.delete')} okType="danger">
                        <Button type="link" danger size="small" icon={<DeleteOutlined />} />
                      </Popconfirm>,
                    ] : [<Tag key="auto" style={{ fontSize: 11 }}>{t('topology.autoLabel')}</Tag>]}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flex: 1, minWidth: 0 }}>
                      <Text ellipsis style={{ maxWidth: 140 }}>{shortName(nodeNameMap.current.get(edge.source) || String(edge.source))}</Text>
                      <span style={{ color: '#999' }}>→</span>
                      <Text ellipsis style={{ maxWidth: 140 }}>{shortName(nodeNameMap.current.get(edge.target) || String(edge.target))}</Text>
                      <Tag color={edge.type === 'calls' ? 'blue' : 'orange'} style={{ marginLeft: 'auto', flexShrink: 0 }}>
                        {edge.type === 'calls' ? t('topology.typeCall') : t('topology.typeDep')}
                      </Tag>
                    </div>
                  </List.Item>
                )}
              />
            )}
          </>
        ) : (
          /* AI 推荐 Tab */
          <>
            <Button
              type="primary" icon={<RobotOutlined />} onClick={requestAISuggest}
              loading={aiLoading} block style={{ marginBottom: 16, background: '#36cfc9', borderColor: '#36cfc9' }}
            >
              {aiLoading ? t('topology.aiAnalyzing') : t('topology.aiAnalyzeButton')}
            </Button>

            {aiMessage && <Paragraph type="secondary"><BulbOutlined /> {aiMessage}</Paragraph>}

            {aiSuggestions.length > 0 && (
              <Button type="primary" ghost icon={<CheckOutlined />} onClick={applyAllSuggestions} block style={{ marginBottom: 12 }}>
                {t('topology.applyAll', { count: aiSuggestions.length })}
              </Button>
            )}

            {aiLoading ? (
              <div style={{ textAlign: 'center', padding: 40 }}><Spin size="large" /><Paragraph style={{ marginTop: 16 }}>{t('topology.aiAnalyzingService')}</Paragraph></div>
            ) : aiSuggestions.length === 0 ? (
              <Empty description={t('topology.noRecommendations')} />
            ) : (
              <List
                size="small"
                dataSource={aiSuggestions}
                renderItem={(item) => (
                  <List.Item
                    actions={[
                      <Button key="apply" type="link" icon={<CheckOutlined />} onClick={() => applyOneSuggestion(item)}>{t('topology.applyButton')}</Button>,
                      <Button key="ignore" type="link" danger icon={<CloseOutlined />}
                        onClick={() => setAiSuggestions(prev => prev.filter(x => x !== item))}>{t('topology.ignoreButton')}</Button>,
                    ]}
                  >
                    <List.Item.Meta
                      title={
                        <Space size={4}>
                          <Text strong style={{ fontSize: 13 }}>{shortName(nodeNameMap.current.get(item.source) || '')}</Text>
                          <span style={{ color: '#999' }}>→</span>
                          <Text strong style={{ fontSize: 13 }}>{shortName(nodeNameMap.current.get(item.target) || '')}</Text>
                          <Tag color={item.type === 'calls' ? 'blue' : 'orange'} style={{ fontSize: 11 }}>
                            {item.type === 'calls' ? t('topology.typeCall') : t('topology.typeDep')}
                          </Tag>
                        </Space>
                      }
                      description={<Text type="secondary" style={{ fontSize: 12 }}>{item.description}</Text>}
                    />
                  </List.Item>
                )}
              />
            )}
          </>
        )}
      </Drawer>
    </div>
  );
}
