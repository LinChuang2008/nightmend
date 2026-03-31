/**
 * SLA 管理页面
 *
 * 包含三个 Tab：
 * 1. SLA 看板 - 展示每个 SLA 规则的实时可用率、错误预算和趋势图
 * 2. 违规事件 - 展示 SLA 违规事件列表，支持按时间筛选
 * 3. 添加 SLA 规则 - 管理 SLA 规则的创建和删除
 */
import { useEffect, useState } from 'react';
import {
  Card, Tabs, Table, Form, Select, InputNumber, Button, Row, Col,
  Progress, Typography, Space, message, Popconfirm, DatePicker, Tag, Empty, Spin,
} from 'antd';
import { DeleteOutlined } from '@ant-design/icons';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';
import ReactECharts from '../components/ThemedECharts';
import api from '../services/api';

const { Title, Text } = Typography;
const { RangePicker } = DatePicker;

/** SLA 规则类型 */
interface SLARule {
  id: number;
  service_id: number;
  name: string;
  target_percent: number;
  calculation_window: string;
  service_name?: string;
  created_at: string;
  updated_at: string;
}

/** SLA 状态类型 */
interface SLAStatus {
  rule_id: number;
  service_id: number;
  service_name: string;
  target_percent: number;
  actual_percent: number | null;
  is_met: boolean | null;
  error_budget_remaining_minutes: number | null;
  calculation_window: string;
  total_checks: number;
  down_checks: number;
}

/** 违规事件类型 */
interface Violation {
  id: number;
  sla_rule_id: number;
  service_id: number;
  service_name?: string;
  started_at: string;
  ended_at?: string;
  duration_seconds?: number;
  description?: string;
  created_at: string;
}

/** 服务类型 */
interface ServiceItem {
  id: number;
  name: string;
}

/** 报告中每日可用率 */
interface DailyAvailability {
  date: string;
  availability: number | null;
}

export default function SLA() {
  const { t } = useTranslation();

  // ========== 看板状态 ==========
  const [statusList, setStatusList] = useState<SLAStatus[]>([]);
  const [statusLoading, setStatusLoading] = useState(false);
  const [trendData, setTrendData] = useState<Record<number, DailyAvailability[]>>({});

  // ========== 违规事件状态 ==========
  const [violations, setViolations] = useState<Violation[]>([]);
  const [violLoading, setViolLoading] = useState(false);
  const [violDates, setViolDates] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null);

  // ========== 规则管理状态 ==========
  const [rules, setRules] = useState<SLARule[]>([]);
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [form] = Form.useForm();

  /** 加载 SLA 状态看板数据 */
  const loadStatus = async () => {
    setStatusLoading(true);
    try {
      const res = await api.get('/sla/status');
      setStatusList(Array.isArray(res.data) ? res.data : []);
      // 为每个有数据的服务加载 30 天趋势
      for (const s of res.data) {
        try {
          const end = dayjs().format('YYYY-MM-DD');
          const start = dayjs().subtract(29, 'day').format('YYYY-MM-DD');
          const rpt = await api.get('/sla/report', {
            params: { service_id: s.service_id, start_date: start, end_date: end },
          });
          setTrendData(prev => ({ ...prev, [s.service_id]: rpt.data.daily_trend }));
        } catch { /* 忽略趋势加载失败 */ }
      }
    } catch {
      message.error(t('sla.loadStatusFailed'));
    }
    setStatusLoading(false);
  };

  /** 加载违规事件 */
  const loadViolations = async () => {
    setViolLoading(true);
    try {
      const params: Record<string, string> = {};
      if (violDates) {
        params.start_date = violDates[0].format('YYYY-MM-DD');
        params.end_date = violDates[1].format('YYYY-MM-DD');
      }
      const res = await api.get('/sla/violations', { params });
      setViolations(Array.isArray(res.data) ? res.data : []);
    } catch {
      message.error(t('sla.loadViolationsFailed'));
    }
    setViolLoading(false);
  };

  /** 加载规则列表和服务列表 */
  const loadRules = async () => {
    setRulesLoading(true);
    try {
      const [rulesRes, svcRes] = await Promise.all([
        api.get('/sla/rules'),
        api.get('/services'),
      ]);
      setRules(Array.isArray(rulesRes.data) ? rulesRes.data : []);
      const svcData = svcRes.data;
      setServices(Array.isArray(svcData?.items) ? svcData.items : Array.isArray(svcData) ? svcData : []);
    } catch {
      message.error(t('sla.loadRulesFailed'));
    }
    setRulesLoading(false);
  };

  useEffect(() => {
    loadStatus();
    loadViolations();
    loadRules();
  }, []);

  /** 创建 SLA 规则 */
  const handleCreate = async (values: any) => {
    try {
      const svc = services.find(s => s.id === values.service_id);
      await api.post('/sla/rules', {
        ...values,
        name: svc ? `${svc.name}${t('sla.ruleSuffix')}` : 'SLA',
      });
      message.success(t('sla.createSuccess'));
      form.resetFields();
      loadRules();
      loadStatus();
    } catch (err: any) {
      message.error(err.response?.data?.detail || t('sla.createFailed'));
    }
  };

  /** 删除 SLA 规则 */
  const handleDelete = async (id: number) => {
    try {
      await api.delete(`/sla/rules/${id}`);
      message.success(t('sla.deleted'));
      loadRules();
      loadStatus();
    } catch {
      message.error(t('sla.deleteFailed'));
    }
  };

  /** 计算错误预算百分比（用于进度条） */
  const getBudgetPercent = (s: SLAStatus): number => {
    if (s.error_budget_remaining_minutes == null) return 100;
    const windowDays = s.calculation_window === 'daily' ? 1 : s.calculation_window === 'weekly' ? 7 : 30;
    const totalMinutes = windowDays * 24 * 60;
    const allowed = totalMinutes * (1 - s.target_percent / 100);
    if (allowed <= 0) return 0;
    return Math.max(0, Math.min(100, Math.round((s.error_budget_remaining_minutes / allowed) * 100)));
  };

  /** 获取错误预算进度条颜色 */
  const getBudgetColor = (pct: number): string => {
    if (pct > 60) return '#52c41a';
    if (pct > 30) return '#faad14';
    return '#ff4d4f';
  };

  // ========== 看板 Tab ==========
  const renderDashboard = () => (
    <Spin spinning={statusLoading}>
      {statusList.length === 0 ? (
        <Empty description={t('sla.noRules')} />
      ) : (
        <>
          <Row gutter={[16, 16]}>
            {statusList.map(s => {
              const budgetPct = getBudgetPercent(s);
              return (
                <Col xs={24} sm={12} lg={8} key={s.rule_id}>
                  <Card hoverable>
                    <Space direction="vertical" style={{ width: '100%' }} align="center">
                      <Text strong>{s.service_name}</Text>
                      <Text type="secondary">{t('sla.targetLabel')}{s.target_percent}%</Text>
                      {s.actual_percent != null ? (
                        <>
                          <Progress
                            type="circle"
                            percent={Math.min(100, s.actual_percent)}
                            format={() => `${s.actual_percent}%`}
                            strokeColor={s.is_met ? '#52c41a' : '#ff4d4f'}
                            size={120}
                          />
                          <Tag color={s.is_met ? 'green' : 'red'}>
                            {s.is_met ? t('sla.met') : t('sla.notMet')}
                          </Tag>
                          {s.actual_percent === 0 && (
                            <Text type="secondary" style={{ fontSize: 11 }}>
                              {t('sla.zeroExplain', '服务完全不可用或无监控数据')}
                            </Text>
                          )}
                          <div style={{ width: '100%' }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              {t('sla.errorBudgetRemaining')}{s.error_budget_remaining_minutes?.toFixed(1)} {t('common.minute')}
                            </Text>
                            <Progress
                              percent={budgetPct}
                              strokeColor={getBudgetColor(budgetPct)}
                              showInfo={false}
                              size="small"
                            />
                          </div>
                        </>
                      ) : (
                        <Text type="secondary">{t('sla.noCheckData')}</Text>
                      )}
                    </Space>
                  </Card>
                </Col>
              );
            })}
          </Row>

          {/* 30 天趋势图 */}
          {statusList.map(s => {
            const trend = trendData[s.service_id];
            if (!trend || trend.length === 0) return null;
            const option = {
              title: { text: `${s.service_name} - ${t('sla.availabilityTrend')}`, left: 'center', textStyle: { fontSize: 14 } },
              tooltip: { trigger: 'axis' as const },
              xAxis: { type: 'category' as const, data: trend.map(d => d.date.slice(5)) },
              yAxis: { type: 'value' as const, min: 99, max: 100, axisLabel: { formatter: '{value}%' } },
              series: [
                {
                  name: t('sla.availability'),
                  type: 'line' as const,
                  data: trend.map(d => d.availability),
                  smooth: true,
                  markLine: {
                    silent: true,
                    data: [{ yAxis: s.target_percent, name: t('sla.targetLine'), lineStyle: { type: 'dashed' as const, color: '#ff4d4f' } }],
                  },
                },
              ],
            };
            return (
              <Card key={s.service_id} style={{ marginTop: 16 }}>
                <ReactECharts option={option} style={{ height: 300 }} />
              </Card>
            );
          })}
        </>
      )}
    </Spin>
  );

  // ========== 违规事件 Tab ==========
  const violationColumns = [
    {
      title: t('sla.violationTime'), dataIndex: 'started_at', key: 'started_at',
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss'),
    },
    { title: t('sla.violationService'), dataIndex: 'service_name', key: 'service_name' },
    {
      title: t('sla.violationDuration'), dataIndex: 'duration_seconds', key: 'duration',
      render: (v: number | null) => v != null ? t('sla.durationMinutes', { minutes: Math.round(v / 60) }) : '-',
    },
    { title: t('sla.violationDesc'), dataIndex: 'description', key: 'description', render: (v: string) => v || '-' },
  ];

  const renderViolations = () => (
    <div>
      <Space style={{ marginBottom: 16 }}>
        <RangePicker
          value={violDates}
          onChange={(dates) => setViolDates(dates as [dayjs.Dayjs, dayjs.Dayjs] | null)}
        />
        <Button type="primary" onClick={loadViolations}>{t('sla.query')}</Button>
      </Space>
      <Table
        columns={violationColumns}
        dataSource={violations}
        rowKey="id"
        loading={violLoading}
        pagination={{ pageSize: 20 }}
        scroll={{ x: 'max-content' }}
      />
    </div>
  );

  // ========== 规则管理 Tab ==========
  const windowMap: Record<string, string> = {
    monthly: t('sla.monthly'),
    weekly: t('sla.weekly'),
    daily: t('sla.daily'),
  };

  const renderRuleManagement = () => (
    <Spin spinning={rulesLoading}>
      <Card title={t('sla.addRule')} style={{ marginBottom: 16 }}>
        <Form form={form} layout="vertical" onFinish={handleCreate}>
          <Row gutter={16}>
            <Col xs={24} sm={8} md={6}>
              <Form.Item name="service_id" label={t('sla.service')} rules={[{ required: true, message: t('sla.serviceRequired') }]}>
                <Select placeholder={t('sla.service')} style={{ width: '100%' }}>
                  {services.map(s => (
                    <Select.Option key={s.id} value={s.id}>{s.name}</Select.Option>
                  ))}
                </Select>
              </Form.Item>
            </Col>
            <Col xs={24} sm={8} md={6}>
              <Form.Item name="target_percent" label={t('sla.targetPercent')} initialValue={99.9}
                rules={[{ required: true, message: t('sla.targetRequired') }]}>
                <InputNumber min={0} max={100} step={0.01} style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col xs={24} sm={8} md={6}>
              <Form.Item name="calculation_window" label={t('sla.calculationWindow')} initialValue="monthly">
                <Select style={{ width: '100%' }}>
                  <Select.Option value="monthly">{t('sla.monthly')}</Select.Option>
                  <Select.Option value="weekly">{t('sla.weekly')}</Select.Option>
                  <Select.Option value="daily">{t('sla.daily')}</Select.Option>
                </Select>
              </Form.Item>
            </Col>
            <Col xs={24} sm={24} md={6}>
              <Form.Item label=" ">
                <Button type="primary" htmlType="submit" style={{ width: '100%' }}>{t('common.create')}</Button>
              </Form.Item>
            </Col>
          </Row>
        </Form>
      </Card>

      <Card title={t('sla.existingRules')}>
        <Table
          dataSource={rules}
          rowKey="id"
          pagination={false}
          scroll={{ x: 'max-content' }}
          columns={[
            { title: t('sla.service'), dataIndex: 'service_name', key: 'service_name' },
            { title: t('sla.ruleName'), dataIndex: 'name', key: 'name' },
            {
              title: t('sla.targetAvailability'), dataIndex: 'target_percent', key: 'target',
              render: (v: number) => `${v}%`,
            },
            {
              title: t('sla.calculationWindow'), dataIndex: 'calculation_window', key: 'window',
              render: (v: string) => windowMap[v] || v,
            },
            {
              title: t('common.actions'), key: 'action',
              render: (_: any, record: SLARule) => (
                <Popconfirm title={t('sla.confirmDeleteRule')} onConfirm={() => handleDelete(record.id)}>
                  <Button danger icon={<DeleteOutlined />} size="small">{t('common.delete')}</Button>
                </Popconfirm>
              ),
            },
          ]}
        />
      </Card>
    </Spin>
  );

  return (
    <div>
      <Title level={4}>{t('sla.title')}</Title>
      <Tabs
        defaultActiveKey="dashboard"
        items={[
          { key: 'dashboard', label: t('sla.dashboard'), children: renderDashboard() },
          { key: 'violations', label: t('sla.violations'), children: renderViolations() },
          { key: 'rules', label: t('sla.addRule'), children: renderRuleManagement() },
        ]}
      />
    </div>
  );
}
