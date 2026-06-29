/**
 * 服务详情页面
 * 展示单个服务的基本信息、响应时间趋势图、可用率散点图和检查历史记录。
 */
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import PageBreadcrumb from '../components/PageBreadcrumb';
import { Card, Descriptions, Tag, Spin, Typography, Table, Row, Col } from 'antd';
import ReactECharts from '../components/ThemedECharts';
import { useTranslation } from 'react-i18next';
import { serviceService } from '../services/services';
import type { Service, ServiceCheck } from '../services/services';
import api from '../services/api';

export default function ServiceDetail() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const [service, setService] = useState<Service | null>(null);
  const [checks, setChecks] = useState<ServiceCheck[]>([]);
  const [loading, setLoading] = useState(true);
  const [slaInfo, setSlaInfo] = useState<{ target: number; current: number; status: string } | null>(null);

  useEffect(() => {
    if (!id) return;
    const fetchData = async () => {
      setLoading(true);
      try {
        const [sRes, cRes, slaRes] = await Promise.all([
          serviceService.get(id),
          serviceService.getChecks(id, { page_size: 100 }),
          api.get('/sla/status').catch(() => ({ data: [] })),
        ]);
        setService(sRes.data);
        const items = Array.isArray(cRes.data) ? cRes.data : (cRes.data as { items?: ServiceCheck[] }).items || [];
        setChecks(items);
        const slaList = Array.isArray(slaRes.data) ? slaRes.data : (slaRes.data?.items || []);
        const found = slaList.find((s: Record<string, unknown>) => String(s.service_id) === String(id));
        if (found) {
          setSlaInfo({
            target: found.sla_target ?? found.target_percent ?? 99.9,
            current: found.current_uptime ?? found.uptime_percent ?? found.compliance_rate ?? 0,
            status: found.status ?? found.sla_status ?? 'no_data',
          });
        }
      } catch (err) { console.warn('Failed to fetch service data:', err); } finally { setLoading(false); }
    };
    fetchData();
  }, [id]);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;
  if (!service) return <Typography.Text>{t('services.notFound')}</Typography.Text>;

  const isUp = (s: string) => s === 'up' || s === 'healthy';

  const sorted = [...checks].sort((a, b) => new Date(a.checked_at).getTime() - new Date(b.checked_at).getTime());
  const timestamps = sorted.map(c => new Date(c.checked_at).toLocaleTimeString());

  const rtOption = {
    title: { text: t('services.responseTimeTrend'), left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' as const },
    series: [{ type: 'line' as const, data: sorted.map(c => c.response_time_ms), smooth: true, itemStyle: { color: '#10B981' }, areaStyle: { opacity: 0.1 } }],
    grid: { top: 40, bottom: 60, left: 50, right: 20 },
  };

  const uptimeOption = {
    title: { text: t('services.uptimeTrend'), left: 'center', textStyle: { fontSize: 14 } },
    tooltip: { trigger: 'axis' as const },
    xAxis: { type: 'category' as const, data: timestamps, axisLabel: { rotate: 30 } },
    yAxis: { type: 'value' as const, min: 0, max: 1 },
    series: [{
      type: 'scatter' as const,
      data: sorted.map(c => isUp(c.status) ? 1 : 0),
      itemStyle: { color: '#52c41a' },
      symbolSize: 8,
    }],
    grid: { top: 40, bottom: 60, left: 50, right: 20 },
  };

  const serviceUrl = service.target || service.url || '-';
  const serviceType = service.type || service.check_type || '-';
  const serviceIsUp = isUp(service.status);

  const lastCheckTime = checks.length > 0
    ? new Date(checks[0].checked_at).toLocaleString()
    : '-';

  const getSlaStatusLabel = (status: string) => {
    if (status === 'compliant' || status === 'met') return t('services.slaMet');
    if (status === 'no_data') return t('common.noData');
    return t('services.slaNotMet');
  };

  const getSlaStatusColor = (status: string) => {
    if (status === 'compliant' || status === 'met') return 'green';
    if (status === 'no_data') return 'default';
    return 'red';
  };

  return (
    <div>
      <PageBreadcrumb items={[{ label: t('menu.services'), path: '/services' }, { label: service.name }]} />
      <Typography.Title level={4}>{service.name}</Typography.Title>

      <Card style={{ marginBottom: 16 }}>
        <Descriptions column={{ xs: 1, sm: 2, md: 3 }}>
          <Descriptions.Item label="URL">{serviceUrl}</Descriptions.Item>
          <Descriptions.Item label={t('services.checkType')}><Tag>{serviceType.toUpperCase()}</Tag></Descriptions.Item>
          <Descriptions.Item label={t('common.status')}>
            <Tag color={serviceIsUp ? 'success' : 'error'}>{serviceIsUp ? t('common.healthy') : t('common.unhealthy')}</Tag>
          </Descriptions.Item>
          <Descriptions.Item label={t('services.uptime')}>{service.uptime_percent != null ? `${service.uptime_percent}%` : '-'}</Descriptions.Item>
          <Descriptions.Item label={t('services.lastCheck')}>{lastCheckTime}</Descriptions.Item>
          {slaInfo && (
            <Descriptions.Item label={t('services.slaTarget')}>{slaInfo.target}%</Descriptions.Item>
          )}
          {slaInfo && (
            <Descriptions.Item label={t('services.currentCompliance')}>
              <Tag color={slaInfo.current >= slaInfo.target ? 'green' : 'red'}>
                {Number(slaInfo.current).toFixed(2)}%
              </Tag>
              <Tag color={getSlaStatusColor(slaInfo.status)} style={{ marginLeft: 4 }}>
                {getSlaStatusLabel(slaInfo.status)}
              </Tag>
            </Descriptions.Item>
          )}
        </Descriptions>
      </Card>

      <Row gutter={[16, 16]} style={{ marginBottom: 16 }}>
        <Col xs={24} md={12}>
          <Card><ReactECharts option={rtOption} style={{ height: 280 }} /></Card>
        </Col>
        <Col xs={24} md={12}>
          <Card><ReactECharts option={uptimeOption} style={{ height: 280 }} /></Card>
        </Col>
      </Row>

      <Card title={t('services.checkHistoryTitle')}>
        <Table dataSource={checks} rowKey="id" size="small"
          pagination={{ pageSize: 20 }}
          columns={[
            { title: t('common.status'), dataIndex: 'status', render: (s: string) => <Tag color={isUp(s) ? 'success' : 'error'}>{s}</Tag> },
            { title: t('services.responseTime'), dataIndex: 'response_time_ms', render: (v: number) => `${v} ms` },
            { title: t('services.statusCode'), dataIndex: 'status_code', render: (v: number | null) => v || '-' },
            { title: t('services.error'), dataIndex: 'error', render: (v: string | null) => v || '-', ellipsis: true },
            { title: t('services.checkedAt'), dataIndex: 'checked_at', render: (val: string) => new Date(val).toLocaleString() },
          ]} />
      </Card>
    </div>
  );
}
