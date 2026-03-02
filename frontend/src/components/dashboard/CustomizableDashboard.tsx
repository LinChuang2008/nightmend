/**
 * 可定制化仪表盘组件
 * 支持拖拽布局、显示控制、配置保存
 */
import { useEffect, useState, useRef, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { 
  Button, Space, Typography, Dropdown, message, 
  Tooltip 
} from 'antd';
import {
  SettingOutlined, DownloadOutlined,
  DragOutlined, LockOutlined, UnlockOutlined
} from '@ant-design/icons';
import { Responsive } from 'react-grid-layout';

// 使用 Responsive 而不是 WidthProvider 包装的版本
const ResponsiveGridLayout = Responsive;
import api from '../../services/api';
import { fetchLogStats } from '../../services/logs';
import type { LogStats } from '../../services/logs';
import { databaseService } from '../../services/databases';
import type { DatabaseItem } from '../../services/databases';

// 导入组件
import MetricsCards from './MetricsCards';
import ServersOverview from './ServersOverview';
import TrendCharts from './TrendCharts';
import ResourceCharts from './ResourceCharts';
import LogStatsWidget from './LogStats';
import AlertsList from './AlertsList';
import DashboardSettings from './DashboardSettings';
import { EmptyState, ErrorState, PageLoading } from '../StateComponents';

// 导入类型和配置
import type { DashboardConfig, DashboardWidget } from './types';
import { DEFAULT_CONFIG } from './types';

// CSS import for react-grid-layout
import 'react-grid-layout/css/styles.css';
import 'react-resizable/css/styles.css';

const { Title } = Typography;


// 存储配置的 localStorage key
const STORAGE_KEY = 'vigilops-dashboard-config';

/* ==================== 类型定义 ==================== */

interface HostItem {
  id: string;
  hostname: string;
  ip_address?: string;
  status: string;
  cpu_cores?: number;
  memory_total_mb?: number;
  latest_metrics?: {
    cpu_percent: number;
    memory_percent: number;
    disk_percent?: number;
    disk_used_mb?: number;
    disk_total_mb?: number;
    net_send_rate_kb?: number;
    net_recv_rate_kb?: number;
    net_packet_loss_rate?: number;
  };
}

interface DashboardData {
  hosts: { total: number; online: number; offline: number; items: HostItem[] };
  services: { total: number; healthy: number; unhealthy: number };
  alerts: {
    total: number; firing: number;
    items: Array<{ id: string; title: string; severity: string; status: string; fired_at: string }>;
  };
}

interface WsDashboardData {
  timestamp: string;
  hosts: { total: number; online: number; offline: number };
  services: { total: number; up: number; down: number };
  alerts: { total: number; firing: number };
  health_score: number;
}

interface TrendPoint {
  hour: string;
  avg_cpu: number | null;
  avg_mem: number | null;
  alert_count: number;
  error_log_count: number;
}

/* ==================== 主组件 ==================== */

export default function CustomizableDashboard() {
  // 数据状态
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [logStats, setLogStats] = useState<LogStats | null>(null);
  const [dbItems, setDbItems] = useState<DatabaseItem[]>([]);
  const [wsConnected, setWsConnected] = useState(false);
  const [wsData, setWsData] = useState<WsDashboardData | null>(null);
  const [trends, setTrends] = useState<TrendPoint[]>([]);

  // 布局状态
  const [config, setConfig] = useState<DashboardConfig>(DEFAULT_CONFIG);
  const [settingsVisible, setSettingsVisible] = useState(false);
  const [isEditing, setIsEditing] = useState(false);
  const [containerWidth, setContainerWidth] = useState(1200);
  const [debouncedHealthScore, setDebouncedHealthScore] = useState<number>(100);
  const healthScoreTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const navigate = useNavigate();
  const { t } = useTranslation();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 加载配置
  const loadConfig = useCallback(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved) {
        const parsedConfig = JSON.parse(saved);
        setConfig(parsedConfig);
      }
    } catch (error) {
      console.warn('Failed to load dashboard config:', error);
      setConfig(DEFAULT_CONFIG);
    }
  }, []);

  // 保存配置
  const saveConfig = useCallback((newConfig: DashboardConfig) => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(newConfig));
      setConfig(newConfig);
      if (newConfig.settings.autoSave) {
        message.success(t('dashboard.layoutAutoSaved'), 1);
      }
    } catch (error) {
      message.error(t('dashboard.layoutSaveFailed'));
    }
  }, []);

  // 获取仪表盘数据
  const fetchData = useCallback(async () => {
    try {
      const [hostsRes, servicesRes, alertsRes] = await Promise.all([
        api.get('/hosts', { params: { page_size: 100 } }),
        api.get('/services', { params: { page_size: 100 } }),
        api.get('/alerts', { params: { page_size: 10, status: 'firing' } }),
      ]);
      
      const hosts = hostsRes.data;
      const services = servicesRes.data;
      const alerts = alertsRes.data;
      
      setData({
        hosts: {
          total: hosts.total,
          online: hosts.items?.filter((h: HostItem) => h.status === 'online').length || 0,
          offline: hosts.items?.filter((h: HostItem) => h.status === 'offline').length || 0,
          items: hosts.items || [],
        },
        services: {
          total: services.total,
          healthy: services.items?.filter((s: { status: string }) => s.status === 'healthy' || s.status === 'up').length || 0,
          unhealthy: services.items?.filter((s: { status: string }) => s.status !== 'healthy' && s.status !== 'up').length || 0,
        },
        alerts: {
          total: alerts.total,
          firing: alerts.items?.filter((a: { status: string }) => a.status === 'firing').length || 0,
          items: alerts.items || [],
        },
      });
      
      try { 
        setLogStats(await fetchLogStats('1h')); 
      } catch {}
      try { 
        setDbItems((await databaseService.list()).data.databases || []); 
      } catch {}
    } catch (err) {
      setLoadError(err);
    } finally { 
      setLoading(false); 
    }
  }, []);

  // 获取趋势数据
  const fetchTrends = useCallback(async () => {
    try { 
      setTrends((await api.get('/dashboard/trends')).data.trends || []); 
    } catch {}
  }, []);

  // WebSocket 相关函数（保持原有逻辑）
  const startPolling = useCallback(() => {
    if (pollTimerRef.current) return;
    pollTimerRef.current = setInterval(() => { 
      fetchData(); 
      fetchTrends(); 
    }, 30000);
  }, [fetchData, fetchTrends]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) { 
      clearInterval(pollTimerRef.current); 
      pollTimerRef.current = null; 
    }
  }, []);

  const connectWs = useCallback(() => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/api/v1/ws/dashboard`;
    
    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      
      ws.onopen = () => { 
        setWsConnected(true); 
        stopPolling(); 
      };
      ws.onmessage = (e) => { 
        try { 
          setWsData(JSON.parse(e.data)); 
        } catch {} 
      };
      ws.onclose = () => { 
        setWsConnected(false); 
        wsRef.current = null; 
        startPolling();
        reconnectTimerRef.current = setTimeout(connectWs, 5000); 
      };
      ws.onerror = () => { 
        ws.close(); 
      };
    } catch { 
      startPolling();
      reconnectTimerRef.current = setTimeout(connectWs, 5000); 
    }
  }, [startPolling, stopPolling]);

  // P1-2: 健康评分防抖 — 延迟 800ms 更新，避免频繁跳动
  useEffect(() => {
    const rawScore = wsData?.health_score ?? 100;
    if (healthScoreTimerRef.current) clearTimeout(healthScoreTimerRef.current);
    healthScoreTimerRef.current = setTimeout(() => {
      setDebouncedHealthScore(rawScore);
    }, 800);
    return () => {
      if (healthScoreTimerRef.current) clearTimeout(healthScoreTimerRef.current);
    };
  }, [wsData?.health_score]);

  // 布局变更处理
  const handleLayoutChange = useCallback((layout: any) => {
    if (!isEditing) return;
    
    const updatedWidgets = config.layout.widgets.map(widget => {
      const layoutItem = layout.find((l: any) => l.i === widget.id);
      if (layoutItem) {
        return {
          ...widget,
          x: layoutItem.x,
          y: layoutItem.y,
          w: layoutItem.w,
          h: layoutItem.h,
        };
      }
      return widget;
    });

    const newConfig = {
      ...config,
      layout: {
        ...config.layout,
        widgets: updatedWidgets,
        lastModified: Date.now()
      }
    };

    if (config.settings.autoSave) {
      saveConfig(newConfig);
    } else {
      setConfig(newConfig);
    }
  }, [config, isEditing, saveConfig]);

  // 重置布局
  const resetLayout = useCallback(() => {
    saveConfig(DEFAULT_CONFIG);
    message.success(t('dashboard.layoutReset'));
  }, [saveConfig]);

  // 导出 CSV
  const exportCSV = () => {
    if (!data) return;
    
    const rows: any[][] = [
      ['指标', '总数', '正常', '异常'],
      ['服务器', data.hosts.total, data.hosts.online, data.hosts.offline],
      ['服务', data.services.total, data.services.healthy, data.services.unhealthy],
      ['数据库', dbItems.length, dbItems.filter(x => x.status === 'healthy').length, 
       dbItems.filter(x => x.status !== 'healthy' && x.status !== 'unknown').length],
      ['活跃告警', data.alerts.firing, '', ''],
      [], 
      ['服务器', 'CPU%', '内存%', '磁盘%', '上传KB/s', '下载KB/s'],
    ];
    
    data.hosts.items.filter(h => h.latest_metrics).forEach(h => {
      const m = h.latest_metrics!;
      rows.push([
        h.hostname, 
        m.cpu_percent, 
        m.memory_percent, 
        m.disk_percent ?? '', 
        m.net_send_rate_kb ?? '', 
        m.net_recv_rate_kb ?? ''
      ]);
    });
    
    const csv = rows.map(r => r.join(',')).join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a'); 
    a.href = url;
    a.download = `dashboard_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click(); 
    URL.revokeObjectURL(url);
  };

  // 监听容器大小变化（使用 ResizeObserver 准确测量实际可用宽度）
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) setContainerWidth(Math.max(320, width));
    });
    observer.observe(el);
    // 初始设置
    setContainerWidth(Math.max(320, el.getBoundingClientRect().width));
    return () => observer.disconnect();
  }, []);

  // 组件初始化
  useEffect(() => {
    loadConfig();
    fetchData();
    fetchTrends();
    connectWs();
    
    return () => {
      wsRef.current?.close();
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      stopPolling();
    };
  }, [loadConfig, fetchData, fetchTrends, connectWs, stopPolling]);

  // 渲染组件
  const renderWidget = useCallback((widget: DashboardWidget) => {
    if (!data) return null;

    const hostTotal = wsData?.hosts.total ?? data.hosts.total;
    const hostOnline = wsData?.hosts.online ?? data.hosts.online;
    const hostOffline = wsData?.hosts.offline ?? data.hosts.offline;
    const svcTotal = wsData?.services.total ?? data.services.total;
    const svcHealthy = wsData?.services.up ?? data.services.healthy;
    const svcUnhealthy = wsData?.services.down ?? data.services.unhealthy;
    const alertFiring = wsData?.alerts.firing ?? data.alerts.firing;
    // Use debounced health score to avoid rapid visual jumps
    const healthScore = debouncedHealthScore;

    switch (widget.component) {
      case 'MetricsCards':
        return (
          <MetricsCards
            hostTotal={hostTotal}
            hostOnline={hostOnline}
            hostOffline={hostOffline}
            svcTotal={svcTotal}
            svcHealthy={svcHealthy}
            svcUnhealthy={svcUnhealthy}
            alertFiring={alertFiring}
            healthScore={healthScore}
            dbItems={dbItems}
          />
        );
      case 'ServersOverview':
        return <ServersOverview hosts={data.hosts.items} />;
      case 'TrendCharts':
        return <TrendCharts trends={trends} />;
      case 'ResourceCharts':
        return <ResourceCharts hosts={data.hosts.items} />;
      case 'LogStats':
        return <LogStatsWidget logStats={logStats} />;
      case 'AlertsList':
        return <AlertsList alerts={data.alerts.items} />;
      default:
        return null;
    }
  }, [data, dbItems, trends, logStats, wsData]);

  if (loading) {
    return <PageLoading tip={t('dashboard.loadingDashboard')} fullScreen />;
  }

  if (loadError) {
    return <ErrorState error={loadError} onRetry={fetchData} fullScreen />;
  }

  const d = data || { 
    hosts: { total: 0, online: 0, offline: 0, items: [] }, 
    services: { total: 0, healthy: 0, unhealthy: 0 }, 
    alerts: { total: 0, firing: 0, items: [] } 
  };

  if (d.hosts.total === 0 && d.services.total === 0) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '60vh' }}>
        <EmptyState scene="dashboard" onAction={() => navigate('/hosts')} actionText={t('state.empty.dashboard.actionText')} />
      </div>
    );
  }

  // 构建 react-grid-layout 的布局数组
  const layouts = {
    lg: config.layout.widgets
      .filter(w => w.visible)
      .map(w => ({
        i: w.id,
        x: w.x,
        y: w.y,
        w: w.w,
        h: w.h,
        minW: w.minW,
        minH: w.minH,
        maxW: w.maxW,
        maxH: w.maxH,
      }))
  };

  return (
    <div ref={containerRef} style={{ width: '100%', overflow: 'hidden' }}>
      {/* 标题栏 */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Space>
          <Title level={4} style={{ margin: 0 }}>{t('dashboard.systemOverview')}</Title>
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 12, color: '#999' }}>
            <span style={{ 
              width: 8, height: 8, borderRadius: '50%', 
              backgroundColor: wsConnected ? '#52c41a' : '#d9d9d9', 
              display: 'inline-block' 
            }} />
            {wsConnected ? t('dashboard.realtime') : t('dashboard.polling')}
          </span>
          {isEditing && (
            <Tooltip title={t('dashboard.editModeTooltip')}>
              <span style={{ color: '#faad14', fontSize: 12 }}>
                <DragOutlined /> {t('dashboard.editMode')}
              </span>
            </Tooltip>
          )}
        </Space>
        <Space>
          <Tooltip title={isEditing ? t('dashboard.lockLayout') : t('dashboard.unlockLayout')}>
            <Button
              icon={isEditing ? <LockOutlined /> : <UnlockOutlined />}
              onClick={() => setIsEditing(!isEditing)}
              type={isEditing ? "primary" : "default"}
            />
          </Tooltip>
          <Button 
            icon={<SettingOutlined />} 
            onClick={() => setSettingsVisible(true)}
          >
            {t('dashboard.settings')}
          </Button>
          <Dropdown 
            menu={{ 
              items: [{ key: 'csv', label: t('dashboard.exportCsv'), onClick: exportCSV }] 
            }}
          >
            <Button icon={<DownloadOutlined />}>{t('dashboard.exportData')}</Button>
          </Dropdown>
        </Space>
      </div>

      {/* 可拖拽网格布局 */}
      <ResponsiveGridLayout
        className="layout"
        layouts={layouts}
        breakpoints={{ lg: 1200, md: 996, sm: 768, xs: 480, xxs: 0 }}
        cols={{ lg: config.settings.gridCols, md: 10, sm: 6, xs: 4, xxs: 2 }}
        rowHeight={config.settings.rowHeight}
        onLayoutChange={handleLayoutChange}
        margin={[16, 16]}
        width={containerWidth}
      >
        {config.layout.widgets
          .filter(w => w.visible)
          .map(widget => (
            <div key={widget.id}>
              {renderWidget(widget)}
            </div>
          ))
        }
      </ResponsiveGridLayout>

      {/* 设置面板 */}
      <DashboardSettings
        visible={settingsVisible}
        config={config}
        onClose={() => setSettingsVisible(false)}
        onConfigChange={saveConfig}
        onResetLayout={resetLayout}
      />
    </div>
  );
}