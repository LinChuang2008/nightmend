/**
 * Dashboard 可定制化配置类型定义
 */

export interface DashboardWidget {
  id: string;
  title: string;
  component: string;
  visible: boolean;
  x: number;
  y: number;
  w: number;
  h: number;
  minW?: number;
  minH?: number;
  maxW?: number;
  maxH?: number;
}

export interface DashboardLayout {
  widgets: DashboardWidget[];
  lastModified: number;
}

export interface DashboardConfig {
  layout: DashboardLayout;
  settings: {
    gridCols: number;
    rowHeight: number;
    autoSave: boolean;
    compactType: 'vertical' | 'horizontal' | null;
  };
}

// 默认布局配置
export const DEFAULT_WIDGETS: DashboardWidget[] = [
  {
    id: 'metrics-cards',
    title: '核心指标',
    component: 'MetricsCards',
    visible: true,
    x: 0, y: 0, w: 12, h: 5,
    minW: 8, minH: 5
  },
  {
    id: 'servers-overview',
    title: '服务器总览',
    component: 'ServersOverview',
    visible: true,
    x: 0, y: 5, w: 12, h: 4,
    minW: 6, minH: 3
  },
  {
    id: 'trend-charts',
    title: '趋势图表',
    component: 'TrendCharts',
    visible: true,
    x: 0, y: 9, w: 12, h: 3,
    minW: 8, minH: 2
  },
  {
    id: 'resource-charts',
    title: '资源对比',
    component: 'ResourceCharts',
    visible: true,
    x: 0, y: 12, w: 12, h: 6,
    minW: 8, minH: 4
  },
  {
    id: 'log-stats',
    title: '日志统计',
    component: 'LogStats',
    visible: true,
    x: 0, y: 18, w: 12, h: 5,
    minW: 6, minH: 4
  },
  {
    id: 'alerts-list',
    title: '最新告警',
    component: 'AlertsList',
    visible: true,
    x: 0, y: 23, w: 12, h: 4,
    minW: 6, minH: 3
  }
];

export const DEFAULT_CONFIG: DashboardConfig = {
  layout: {
    widgets: DEFAULT_WIDGETS,
    lastModified: Date.now()
  },
  settings: {
    gridCols: 12,
    rowHeight: 60,
    autoSave: true,
    compactType: 'vertical'
  }
};