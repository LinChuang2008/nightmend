/**
 * 告警降噪展示组件 (Alert Noise Reduction Display)
 *
 * 展示告警去重/聚合效果：
 * - 顶部统计卡片：原始数、降噪后数、压缩率
 * - 聚合组列表：展开/折叠查看组内告警
 * - 降噪趋势图 (ECharts)
 */
import { useEffect, useState, useCallback, memo } from 'react';
import { Card, Row, Col, Statistic, Table, Tag, Typography, Spin, Empty, Progress } from 'antd';
import { ThunderboltOutlined, CompressOutlined, TeamOutlined, FilterOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import ReactECharts from './ThemedECharts';
import api from '../services/api';

interface DeduplicationStats {
  active_dedup_records: number;
  active_alert_groups: number;
  deduplication_rate_24h: number;
  suppressed_alerts_24h: number;
  total_alert_occurrences_24h: number;
}

interface AlertGroupItem {
  id: number;
  title: string;
  severity: string;
  status: string;
  alert_count: number;
  rule_count: number;
  host_count: number;
  service_count: number;
  last_occurrence: string;
  window_end: string;
}

const severityColor: Record<string, string> = { critical: 'red', warning: 'orange', info: 'blue' };
const statusColor: Record<string, string> = { firing: 'red', resolved: 'green', acknowledged: 'blue' };

export default memo(function NoiseReduction() {
  const { t } = useTranslation();
  const [stats, setStats] = useState<DeduplicationStats | null>(null);
  const [groups, setGroups] = useState<AlertGroupItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [groupsTotal, setGroupsTotal] = useState(0);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const [statsRes, groupsRes] = await Promise.all([
        api.get('/alert-deduplication/statistics'),
        api.get('/alert-deduplication/groups?limit=50'),
      ]);
      setStats(statsRes.data);
      setGroups(groupsRes.data.groups || []);
      setGroupsTotal(groupsRes.data.total || 0);
    } catch (e) {
      console.error('Failed to load deduplication data', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchData(); }, [fetchData]);

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 60 }}><Spin size="large" tip={t('noiseReduction.loadingData')} /></div>;
  }

  if (!stats) {
    return <Empty description={t('noiseReduction.noData')} />;
  }

  const originalCount = stats.total_alert_occurrences_24h;
  const afterCount = stats.active_alert_groups || groupsTotal;
  // 重新计算压缩率：(1 - 压缩后数量/压缩前数量) * 100，最大 99.9%
  const rate = originalCount > 0
    ? Math.min(99.9, Math.max(0, (1 - afterCount / originalCount) * 100))
    : 0;

  // ── 降噪对比柱状图 ──
  const barOption = {
    tooltip: { trigger: 'axis' as const },
    grid: { left: 40, right: 20, top: 30, bottom: 30 },
    xAxis: {
      type: 'category' as const,
      data: [t('noiseReduction.originalAlerts'), t('noiseReduction.afterReduction')],
    },
    yAxis: { type: 'value' as const },
    series: [
      {
        type: 'bar',
        data: [
          { value: originalCount, itemStyle: { color: '#ff4d4f' } },
          { value: afterCount, itemStyle: { color: '#52c41a' } },
        ],
        barWidth: 60,
        label: { show: true, position: 'top' as const, fontSize: 16, fontWeight: 'bold' as const },
      },
    ],
  };

  // ── 按严重级别分布饼图 ──
  const severityCounts: Record<string, number> = {};
  groups.forEach(g => {
    severityCounts[g.severity] = (severityCounts[g.severity] || 0) + g.alert_count;
  });
  const pieOption = {
    tooltip: { trigger: 'item' as const },
    series: [
      {
        type: 'pie',
        radius: ['40%', '70%'],
        data: Object.entries(severityCounts).map(([name, value]) => ({
          name: name.toUpperCase(),
          value,
          itemStyle: { color: name === 'critical' ? '#ff4d4f' : name === 'warning' ? '#faad14' : '#1890ff' },
        })),
        label: { formatter: '{b}: {c}' },
      },
    ],
  };

  // ── 聚合组表格列定义 ──
  const groupColumns = [
    {
      title: t('noiseReduction.aggregationGroup'),
      dataIndex: 'title',
      key: 'title',
      ellipsis: true,
    },
    {
      title: t('noiseReduction.severity'),
      dataIndex: 'severity',
      key: 'severity',
      width: 100,
      render: (s: string) => <Tag color={severityColor[s]}>{s.toUpperCase()}</Tag>,
    },
    {
      title: t('noiseReduction.status'),
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => <Tag color={statusColor[s]}>{s}</Tag>,
    },
    {
      title: t('noiseReduction.containedAlerts'),
      dataIndex: 'alert_count',
      key: 'alert_count',
      width: 100,
      sorter: (a: AlertGroupItem, b: AlertGroupItem) => a.alert_count - b.alert_count,
      defaultSortOrder: 'descend' as const,
      render: (n: number) => <Typography.Text strong style={{ color: n > 10 ? '#ff4d4f' : '#333' }}>{n}</Typography.Text>,
    },
    {
      title: t('noiseReduction.involvedHosts'),
      dataIndex: 'host_count',
      key: 'host_count',
      width: 90,
    },
    {
      title: t('noiseReduction.lastTriggered'),
      dataIndex: 'last_occurrence',
      key: 'last_occurrence',
      width: 180,
      render: (t: string) => new Date(t).toLocaleString(),
    },
  ];

  return (
    <div>
      {/* ── 顶部统计卡片 ── */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={12} sm={6}>
          <Card hoverable>
            <Statistic
              title={t('noiseReduction.originalAlerts24h')}
              value={originalCount}
              prefix={<ThunderboltOutlined style={{ color: '#ff4d4f' }} />}
              valueStyle={{ color: '#ff4d4f' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable>
            <Statistic
              title={t('noiseReduction.afterReductionGroups')}
              value={afterCount}
              prefix={<CompressOutlined style={{ color: '#52c41a' }} />}
              valueStyle={{ color: '#52c41a' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable>
            <Statistic
              title={t('noiseReduction.suppressedAlerts')}
              value={stats.suppressed_alerts_24h}
              prefix={<FilterOutlined style={{ color: '#1890ff' }} />}
              valueStyle={{ color: '#1890ff' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={6}>
          <Card hoverable style={{ textAlign: 'center' }}>
            <div style={{ marginBottom: 8 }}>
              <Typography.Text type="secondary">{t('noiseReduction.reductionRate')}</Typography.Text>
            </div>
            <Progress
              type="circle"
              percent={Math.round(rate)}
              size={80}
              strokeColor={rate > 80 ? '#52c41a' : rate > 50 ? '#faad14' : '#ff4d4f'}
              format={p => <span style={{ fontSize: 18, fontWeight: 'bold' }}>{p}%</span>}
            />
          </Card>
        </Col>
      </Row>

      {/* ── 对比图表 ── */}
      <Row gutter={[16, 16]} style={{ marginBottom: 24 }}>
        <Col xs={24} md={14}>
          <Card title={t('noiseReduction.comparisonChart')} size="small">
            <ReactECharts option={barOption} style={{ height: 260 }} />
          </Card>
        </Col>
        <Col xs={24} md={10}>
          <Card title={t('noiseReduction.severityDistribution')} size="small">
            <ReactECharts option={pieOption} style={{ height: 260 }} />
          </Card>
        </Col>
      </Row>

      {/* ── 核心数字对比 Banner ── */}
      <Card
        style={{
          marginBottom: 24,
          background: 'var(--nm-surface, #141419)',
          border: '1px solid var(--nm-border, #27272a)',
        }}
      >
        <Row align="middle" justify="center" gutter={24}>
          <Col>
            <Typography.Title level={1} style={{ color: '#ff4d4f', margin: 0 }}>{originalCount}</Typography.Title>
            <Typography.Text type="secondary">{t('noiseReduction.originalAlertsUnit')}</Typography.Text>
          </Col>
          <Col>
            <Typography.Title level={2} style={{ margin: '0 16px', color: '#999' }}>→</Typography.Title>
          </Col>
          <Col>
            <Typography.Title level={1} style={{ color: '#52c41a', margin: 0 }}>{afterCount}</Typography.Title>
            <Typography.Text type="secondary">{t('noiseReduction.aggregationGroupsUnit')}</Typography.Text>
          </Col>
          <Col>
            <Tag color="green" style={{ fontSize: 18, padding: '4px 16px', marginLeft: 16 }}>
              {t('noiseReduction.compressionSummary', { original: originalCount, after: afterCount, rate: rate.toFixed(1) })}
            </Tag>
          </Col>
        </Row>
      </Card>

      {/* ── 聚合组列表 ── */}
      <Card title={<><TeamOutlined /> {t('noiseReduction.alertGroups', { count: groupsTotal })}</>}>
        <Table
          dataSource={groups}
          columns={groupColumns}
          rowKey="id"
          pagination={{ pageSize: 10 }}
          expandable={{
            expandedRowRender: (record) => (
              <div style={{ padding: '8px 0' }}>
                <Typography.Text type="secondary">
                  {t('noiseReduction.groupDetail', { id: record.id, alerts: record.alert_count, hosts: record.host_count, rules: record.rule_count })}
                </Typography.Text>
                <br />
                <Typography.Text type="secondary">
                  {t('noiseReduction.windowEnd')}: {new Date(record.window_end).toLocaleString()}
                </Typography.Text>
              </div>
            ),
          }}
        />
      </Card>
    </div>
  );
})
