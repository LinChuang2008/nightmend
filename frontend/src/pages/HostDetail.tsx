/**
 * 主机详情页面
 * 展示单台主机的基本信息和性能监控图表，包括 CPU、内存、磁盘使用率，
 * 网络流量、网络带宽和丢包率等指标，支持时间范围切换，每 30 秒自动刷新。
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import PageBreadcrumb from '../components/PageBreadcrumb';
import { Card, Row, Col, Descriptions, Tag, Spin, Typography, Select, Space } from 'antd';
import ReactECharts from '../components/ThemedECharts';
import { useTranslation } from 'react-i18next';
import { hostService } from '../services/hosts';
import type { Host, HostMetrics } from '../services/hosts';
import api from '../services/api';

/**
 * 主机详情组件
 */
export default function HostDetail() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [host, setHost] = useState<Host | null>(null);
  const [metrics, setMetrics] = useState<HostMetrics[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('1h');
  const [alerts, setAlerts] = useState<{ id: string; title: string; severity: string; fired_at: string }[]>([]);

  const fetchData = async () => {
    if (!id) return;
    setLoading(true);
    try {
      const [hostRes, metricsRes, alertsRes] = await Promise.all([
        hostService.get(id),
        hostService.getMetrics(id, { range: timeRange }),
        api.get(`/alerts`, { params: { host_id: id, status: 'firing', page_size: 20 } }).catch(() => ({ data: { items: [] } })),
      ]);
      setHost(hostRes.data);
      setMetrics(Array.isArray(metricsRes.data) ? metricsRes.data : []);
      const items = alertsRes.data?.items || (Array.isArray(alertsRes.data) ? alertsRes.data : []);
      setAlerts(items);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchData(); }, [id, timeRange]);

  useEffect(() => {
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [id, timeRange]);

  if (loading && !host) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!host) return <Typography.Text>{t('hosts.notFound')}</Typography.Text>;

  const timestamps = metrics.map(m => {
    const ts = (m as Record<string, unknown>).recorded_at || m.timestamp;
    return ts ? new Date(ts as string).toLocaleTimeString() : '';
  });

  const lineOption = (title: string, series: { name: string; data: number[]; color: string }[]) => ({
    title: { text: title, left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' as const },
    legend: { bottom: 0 },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' as const, axisLabel: { formatter: '{value}%' } },
    series: series.map(s => ({ ...s, type: 'line' as const, smooth: true, areaStyle: { opacity: 0.1 } })),
    grid: { top: 40, bottom: 60, left: 50, right: 20 },
  });

  const netOption = {
    title: { text: t('hosts.networkTraffic'), left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' as const },
    legend: { bottom: 0 },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' as const, axisLabel: { formatter: (v: number) => `${(v / 1024).toFixed(0)} KB` } },
    series: [
      { name: t('hosts.sent'), type: 'line' as const, data: metrics.map(m => m.net_bytes_sent), smooth: true, itemStyle: { color: '#1677ff' } },
      { name: t('hosts.recv'), type: 'line' as const, data: metrics.map(m => m.net_bytes_recv), smooth: true, itemStyle: { color: '#52c41a' } },
    ],
    grid: { top: 40, bottom: 60, left: 70, right: 20 },
  };

  const netRateOption = {
    title: { text: t('hosts.networkBandwidth'), left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' as const },
    legend: { bottom: 0 },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' as const, axisLabel: { formatter: '{value} KB/s' } },
    series: [
      { name: t('hosts.upload'), type: 'line' as const, data: metrics.map(m => Math.max(0, m.net_send_rate_kb ?? 0)), smooth: true, areaStyle: { opacity: 0.1 }, itemStyle: { color: '#1677ff' } },
      { name: t('hosts.download'), type: 'line' as const, data: metrics.map(m => Math.max(0, m.net_recv_rate_kb ?? 0)), smooth: true, areaStyle: { opacity: 0.1 }, itemStyle: { color: '#52c41a' } },
    ],
    grid: { top: 40, bottom: 60, left: 60, right: 20 },
  };

  const packetLossOption = {
    title: { text: t('hosts.packetLoss'), left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' as const, axisLabel: { formatter: '{value}%' } },
    series: [
      { name: t('hosts.packetLoss'), type: 'line' as const, data: metrics.map(m => m.net_packet_loss_rate ?? 0), smooth: true, areaStyle: { opacity: 0.15 }, itemStyle: { color: '#faad14' } },
    ],
    grid: { top: 40, bottom: 40, left: 50, right: 20 },
  };

  return (
    <div>
      <PageBreadcrumb items={[{ label: t('menu.hosts'), path: '/hosts' }, { label: host.hostname }]} />
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col><Typography.Title level={4} style={{ margin: 0 }}>{host.hostname}</Typography.Title></Col>
        <Col>
          <Space>
            <Typography.Text type="secondary">{t('hosts.timeRange')}:</Typography.Text>
            <Select value={timeRange} onChange={setTimeRange} style={{ width: 120 }}
              options={[
                { label: t('hosts.oneHour'), value: '1h' },
                { label: t('hosts.sixHours'), value: '6h' },
                { label: t('hosts.twentyFourHours'), value: '24h' },
                { label: t('hosts.sevenDays'), value: '7d' },
              ]} />
          </Space>
        </Col>
      </Row>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={{ xs: 1, sm: 2, md: 3 }}>
          <Descriptions.Item label={t('hosts.displayName')}>{host.display_name || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('hosts.hostname')}>{host.hostname}</Descriptions.Item>
          <Descriptions.Item label={t('hosts.publicIp')}>{host.public_ip || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('hosts.privateIp')}>{host.private_ip || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('hosts.os')}>{host.os || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('hosts.status')}>
            <Tag color={host.status === 'online' ? 'success' : 'error'}>{host.status === 'online' ? t('hosts.online') : t('hosts.offline')}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('hosts.group')}>{host.group_name || '-'}</Descriptions.Item>
          <Descriptions.Item label={t('hosts.lastHeartbeat')}>{host.last_heartbeat ? new Date(host.last_heartbeat).toLocaleString() : '-'}</Descriptions.Item>
          <Descriptions.Item label={t('hosts.tags')}>
            {host.tags ? (Array.isArray(host.tags) ? host.tags : Object.keys(host.tags)).map((tag: string) => <Tag key={tag}>{tag}</Tag>) : '-'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* 活跃告警卡片 */}
      {alerts.length > 0 ? (
        <Card
          style={{ marginBottom: 16, borderColor: '#ff4d4f', borderWidth: 1.5 }}
          title={<Typography.Text strong style={{ color: '#ff4d4f' }}>⚠️ {t('hosts.activeAlerts', { count: alerts.length })}</Typography.Text>}
          size="small"
        >
          {alerts.map(a => (
            <div key={a.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '6px 0', borderBottom: '1px solid #f0f0f0' }}>
              <span style={{ flex: 1, fontWeight: 500 }}>{a.title}</span>
              <Tag color={a.severity === 'critical' ? 'red' : a.severity === 'warning' ? 'orange' : 'blue'}>{a.severity}</Tag>
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>{new Date(a.fired_at).toLocaleString()}</Typography.Text>
            </div>
          ))}
        </Card>
      ) : (
        <div style={{ marginBottom: 16 }}>
          <Tag color="success">{t('hosts.noActiveAlerts')}</Tag>
        </div>
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} md={12}>
          <Card>
            <ReactECharts option={lineOption(t('hosts.cpuUsage'), [
              { name: 'CPU', data: metrics.map(m => m.cpu_percent), color: '#1677ff' },
            ])} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card>
            <ReactECharts option={lineOption(t('hosts.memoryUsage'), [
              { name: t('hosts.memory'), data: metrics.map(m => m.memory_percent), color: '#52c41a' },
            ])} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card>
            <ReactECharts option={lineOption(t('hosts.diskUsage'), [
              { name: t('hosts.disk'), data: metrics.map(m => m.disk_percent), color: '#faad14' },
            ])} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card>
            <ReactECharts option={netOption} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card>
            <ReactECharts option={netRateOption} style={{ height: 280 }} />
          </Card>
        </Col>
        <Col xs={24} md={12}>
          <Card>
            <ReactECharts option={packetLossOption} style={{ height: 280 }} />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
