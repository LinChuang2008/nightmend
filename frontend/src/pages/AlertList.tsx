/**
 * 告警中心页面
 *
 * 包含两个 Tab：
 * 1. 告警列表 - 展示所有告警，支持按状态和严重级别筛选，可查看详情、确认告警、触发 AI 根因分析
 * 2. 告警规则 - 管理告警规则（指标告警、日志关键字告警、数据库告警），支持增删改及静默时段设置
 */
import { useEffect, useState, useRef } from 'react';
import { useResponsive } from '../hooks/useResponsive';
import { Table, Card, Tag, Typography, Select, Space, Button, Drawer, Descriptions, Tabs, Modal, Form, Input, InputNumber, Switch, Row, Col, message, TimePicker, Spin, Empty, Collapse, Radio, Tooltip, Dropdown } from 'antd';
import { ExclamationCircleOutlined, RobotOutlined, PauseCircleOutlined, PlayCircleOutlined, MoreOutlined, EyeOutlined, CheckCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import api from '../services/api';
import { alertService } from '../services/alerts';
import { databaseService } from '../services/databases';
import type { DatabaseItem } from '../services/databases';
import type { Alert, AlertRule } from '../services/alerts';
// RemediationStatusTag replaced by inline i18n render below
import { ErrorState } from '../components/StateComponents';
import NoiseReduction from '../components/NoiseReduction';
import PageHeader from '../components/PageHeader';

const severityColor: Record<string, string> = { critical: 'red', warning: 'orange', info: 'blue' };
const statusColor: Record<string, string> = { firing: 'red', resolved: 'green', acknowledged: 'blue' };

export default function AlertList() {
  const { t, i18n } = useTranslation();
  const { isMobile } = useResponsive();
  const getAlertTitle = (alert: Alert) =>
    i18n.language === 'en' && alert.title_en ? alert.title_en : alert.title;
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [severityFilter, setSeverityFilter] = useState<string>('');
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null);
  const [rules, setRules] = useState<AlertRule[]>([]);
  const [rulesLoading, setRulesLoading] = useState(false);
  const [ruleModalOpen, setRuleModalOpen] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
  const [ruleType, setRuleType] = useState<string>('metric');
  const [dbList, setDbList] = useState<DatabaseItem[]>([]);
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();

  const [rcModalOpen, setRcModalOpen] = useState(false);
  const [rcLoading, setRcLoading] = useState(false);
  const [rcData, setRcData] = useState<{ root_cause: string; confidence: string; evidence: string[]; recommendations: string[] } | null>(null);

  const aiCacheRef = useRef<Record<string, string>>({});
  const [drawerAiLoading, setDrawerAiLoading] = useState(false);
  const [drawerAiResult, setDrawerAiResult] = useState<string | null>(null);

  // ===== 告警静默 =====
  const [silenceModalOpen, setSilenceModalOpen] = useState(false);
  const [silenceTarget, setSilenceTarget] = useState<Alert | null>(null);
  const [silenceDuration, setSilenceDuration] = useState<number>(1);
  const [silenceCustomHours, setSilenceCustomHours] = useState<number>(1);
  const [silenceLoading, setSilenceLoading] = useState(false);
  const [silenceRules, setSilenceRules] = useState<Record<string, AlertRule>>({});

  const handleRootCause = async (alertId: string) => {
    setRcData(null);
    setRcModalOpen(true);
    setRcLoading(true);
    try {
      const { data } = await api.post(`/ai/root-cause?alert_id=${alertId}`);
      setRcData(data);
    } catch {
      messageApi.error(t('alerts.analysisFailed'));
      setRcModalOpen(false);
    } finally { setRcLoading(false); }
  };

  const handleDrawerAiAnalyze = async (alertId: string) => {
    if (aiCacheRef.current[alertId]) {
      setDrawerAiResult(aiCacheRef.current[alertId]);
      return;
    }
    setDrawerAiLoading(true);
    setDrawerAiResult(null);
    try {
      const { data } = await api.get(`/ai/analyze`, { params: { alert_id: alertId } }).catch(() =>
        api.get(`/ai/insights`, { params: { alert_id: alertId } })
      );
      const text = data?.summary || data?.analysis || data?.root_cause || JSON.stringify(data);
      aiCacheRef.current[alertId] = text;
      setDrawerAiResult(text);
    } catch {
      setDrawerAiResult(t('aiAnalysis.aiUnavailable'));
    } finally {
      setDrawerAiLoading(false);
    }
  };

  // 打开静默 Modal
  const openSilenceModal = async (alert: Alert) => {
    setSilenceTarget(alert);
    setSilenceDuration(1);
    setSilenceCustomHours(1);
    setSilenceModalOpen(true);
    // 如果尚未加载该规则，则拉取
    if (alert.rule_id && !silenceRules[alert.rule_id]) {
      try {
        const { data } = await api.get<AlertRule>(`/alert-rules/${alert.rule_id}`);
        setSilenceRules(prev => ({ ...prev, [alert.rule_id]: data }));
      } catch { /* ignore */ }
    }
  };

  // 执行静默
  const handleSilence = async () => {
    if (!silenceTarget) return;
    const hours = silenceDuration === -1 ? silenceCustomHours : silenceDuration;
    const now = new Date();
    const end = new Date(now.getTime() + hours * 60 * 60 * 1000);
    const pad = (n: number) => String(n).padStart(2, '0');
    const startStr = `${pad(now.getHours())}:${pad(now.getMinutes())}:00`;
    const endStr = `${pad(end.getHours())}:${pad(end.getMinutes())}:00`;

    setSilenceLoading(true);
    try {
      await alertService.updateRule(silenceTarget.rule_id, {
        silence_start: startStr,
        silence_end: endStr,
      });
      messageApi.success(t('alertSilence.silenceSuccess', { hours }));
      setSilenceModalOpen(false);
      fetchAlerts();
    } catch {
      messageApi.error(t('alertSilence.silenceFailed'));
    } finally {
      setSilenceLoading(false);
    }
  };

  // 解除静默（传入 rule_id 直接操作）
  const handleLiftSilence = async (ruleId: string) => {
    try {
      await alertService.updateRule(ruleId, { silence_start: null, silence_end: null });
      messageApi.success(t('alertSilence.liftSuccess'));
      fetchAlerts();
    } catch {
      messageApi.error(t('alertSilence.silenceFailed'));
    }
  };

  // 判断某 alert 对应的规则是否正在静默中
  const isRuleSilenced = (alert: Alert): boolean => {
    const rule = silenceRules[alert.rule_id];
    if (!rule || !rule.silence_start || !rule.silence_end) return false;
    const now = new Date();
    const pad = (n: number) => String(n).padStart(2, '0');
    const nowStr = `${pad(now.getHours())}:${pad(now.getMinutes())}:00`;
    const s = rule.silence_start;
    const e = rule.silence_end;
    if (s <= e) return nowStr >= s && nowStr <= e;
    return nowStr >= s || nowStr <= e; // midnight crossing
  };

  const fetchAlerts = async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const params: Record<string, unknown> = { page, page_size: 20 };
      if (statusFilter) params.status = statusFilter;
      if (severityFilter) params.severity = severityFilter;
      const { data } = await alertService.list(params);
      const items: Alert[] = data.items || [];
      setAlerts(items);
      setTotal(data.total || 0);
      // 预加载各告警对应的规则（用于显示静默状态）
      const uniqueRuleIds = [...new Set(items.map(a => a.rule_id).filter(Boolean))];
      const ruleResults = await Promise.allSettled(
        uniqueRuleIds.map(id => api.get<AlertRule>(`/alert-rules/${id}`))
      );
      const newRules: Record<string, AlertRule> = {};
      ruleResults.forEach((r, idx) => {
        if (r.status === 'fulfilled') newRules[uniqueRuleIds[idx]] = r.value.data;
      });
      setSilenceRules(prev => ({ ...prev, ...newRules }));
    } catch (err) { setLoadError(err); } finally { setLoading(false); }
  };

  const fetchRules = async () => {
    setRulesLoading(true);
    try {
      const { data } = await alertService.listRules();
      setRules(Array.isArray(data) ? data : []);
    } catch { /* ignore */ } finally { setRulesLoading(false); }
  };

  const loadDbList = async () => {
    try {
      const { data } = await databaseService.list();
      setDbList(data.databases || []);
    } catch { /* ignore */ }
  };

  useEffect(() => { fetchAlerts(); }, [page, statusFilter, severityFilter]);

  const handleAck = async (id: string) => {
    try {
      await alertService.ack(id);
      messageApi.success(t('alerts.acknowledged'));
      fetchAlerts();
      setSelectedAlert(null);
    } catch { messageApi.error(t('common.failed')); }
  };

  const handleRuleSave = async (values: Record<string, unknown>) => {
    const payload = { ...values } as Record<string, unknown>;
    payload.silence_start = values.silence_start ? (values.silence_start as dayjs.Dayjs).format('HH:mm:ss') : null;
    payload.silence_end = values.silence_end ? (values.silence_end as dayjs.Dayjs).format('HH:mm:ss') : null;
    try {
      if (editingRule) {
        await alertService.updateRule(editingRule.id, payload as Partial<AlertRule>);
      } else {
        await alertService.createRule(payload as Partial<AlertRule>);
      }
      messageApi.success(t('alerts.saveSuccess'));
      setRuleModalOpen(false);
      fetchRules();
    } catch { messageApi.error(t('alerts.saveFailed')); }
  };

  const handleRuleDelete = (id: string) => {
    Modal.confirm({
      title: t('alerts.confirmDeleteRule'),
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        try {
          await alertService.deleteRule(id);
          messageApi.success(t('alerts.deleted'));
          fetchRules();
        } catch { messageApi.error(t('alerts.deleteFailed')); }
      },
    });
  };

  const alertColumns = [
    { title: t('alerts.title_field'), key: 'title', ellipsis: true, render: (_: unknown, record: Alert) => getAlertTitle(record) },
    { title: t('alerts.severity'), dataIndex: 'severity', render: (s: string) => <Tag color={severityColor[s]}>{t(`alerts.severityLevels.${s}`) || s}</Tag> },
    { title: t('alerts.status'), dataIndex: 'status', render: (s: string) => <Tag color={statusColor[s]}>{t(`alerts.statusTypes.${s}`) || s}</Tag> },
    { title: t('alerts.triggeredAt'), dataIndex: 'fired_at', render: (val: string) => new Date(val).toLocaleString() },
    {
      title: t('alerts.remediationStatus'), dataIndex: 'remediation_status', key: 'remediation_status',
      render: (s: string) => {
        if (!s) return <span style={{ color: '#999' }}>-</span>;
        const remediationColorMap: Record<string, string> = {
          pending: 'orange', approved: 'blue', executing: 'processing',
          success: 'success', failed: 'error', rejected: 'default',
        };
        const color = remediationColorMap[s] || 'default';
        const labelKeyMap: Record<string, string> = {
          pending: 'remediation.statusPending', approved: 'remediation.statusApproved',
          executing: 'remediation.statusExecuting', success: 'remediation.statusSuccess',
          failed: 'remediation.statusFailed', rejected: 'remediation.statusRejected',
        };
        const label = labelKeyMap[s] ? t(labelKeyMap[s]) : s;
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: t('common.actions'), key: 'action', width: 140,
      render: (_: unknown, record: Alert) => {
        const silenced = isRuleSilenced(record);
        const moreMenuItems = [
          {
            key: 'ai-analysis',
            label: t('alerts.aiAnalysis'),
            icon: <RobotOutlined />,
            onClick: () => handleRootCause(record.id),
          },
          {
            key: 'silence',
            label: silenced ? t('alertSilence.liftSilence') : t('alertSilence.silence'),
            icon: silenced ? <PlayCircleOutlined /> : <PauseCircleOutlined />,
            onClick: () => silenced ? handleLiftSilence(record.rule_id) : openSilenceModal(record),
          },
        ];

        return (
          <Space>
            <Button 
              type="primary" 
              size="small" 
              icon={<EyeOutlined />} 
              onClick={() => setSelectedAlert(record)}
            >
              {t('common.detail')}
            </Button>
            {record.status === 'firing' && (
              <Button 
                type="default" 
                size="small" 
                icon={<CheckCircleOutlined />} 
                onClick={() => handleAck(record.id)}
              >
                {t('alerts.acknowledge')}
              </Button>
            )}
            <Dropdown menu={{ items: moreMenuItems }}>
              <Button type="text" size="small" icon={<MoreOutlined />} />
            </Dropdown>
          </Space>
        );
      },
    },
  ];

  const mobileAlertColumns = [
    {
      title: t('alerts.alertInfo'),
      key: 'info',
      render: (_: unknown, record: Alert) => (
        <div>
          <div style={{ fontWeight: 500, marginBottom: 4 }}>{getAlertTitle(record)}</div>
          <Space size="small" wrap>
            <Tag color={severityColor[record.severity]}>{record.severity}</Tag>
            <Tag color={statusColor[record.status]}>{record.status}</Tag>
            <span style={{ fontSize: '12px', color: '#666' }}>
              {new Date(record.fired_at).toLocaleString()}
            </span>
          </Space>
        </div>
      )
    },
    {
      title: t('common.actions'), key: 'action', width: 80,
      render: (_: unknown, record: Alert) => (
        <Space direction="vertical" size="small">
          <Button type="primary" size="small" onClick={() => setSelectedAlert(record)}>{t('common.detail')}</Button>
          {record.status === 'firing' && (
            <Button size="small" onClick={() => handleAck(record.id)}>{t('alerts.acknowledge')}</Button>
          )}
        </Space>
      ),
    },
  ];

  const ruleTypeColor: Record<string, string> = { metric: 'blue', log_keyword: 'purple', db_metric: 'cyan' };

  const ruleColumns = [
    { title: t('alerts.rules.name'), dataIndex: 'name' },
    {
      title: t('alerts.rules.type'), dataIndex: 'rule_type', key: 'rule_type',
      render: (ruleT: string) => {
        const label = ruleT === 'metric' ? t('alerts.rules.metric')
          : ruleT === 'log_keyword' ? t('alerts.rules.logKeyword')
          : ruleT === 'db_metric' ? t('alerts.rules.database')
          : ruleT || t('alerts.rules.metric');
        return <Tag color={ruleTypeColor[ruleT] || 'default'}>{label}</Tag>;
      },
    },
    {
      title: t('alerts.rules.condition'), key: 'cond',
      render: (_: unknown, r: AlertRule) => {
        const rt = r.rule_type || 'metric';
        if (rt === 'log_keyword') return `${t('alerts.rules.matchKeyword')}: ${r.log_keyword || '-'}`;
        if (rt === 'db_metric') return `${r.db_metric_name || '-'} ${r.operator} ${r.threshold}`;
        return `${r.metric} ${r.operator} ${r.threshold}`;
      },
    },
    { title: t('alerts.filterLevel'), dataIndex: 'severity', render: (s: string) => <Tag color={severityColor[s]}>{s}</Tag> },
    { title: t('alerts.rules.enabled'), dataIndex: 'is_enabled', render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? t('common.yes') : t('common.no')}</Tag> },
    {
      title: t('common.actions'), key: 'action',
      render: (_: unknown, r: AlertRule) => (
        <Space>
          <Button type="link" size="small" onClick={() => {
            setEditingRule(r);
            setRuleType(r.rule_type || 'metric');
            const vals = { ...r } as Record<string, unknown>;
            if (r.silence_start) vals.silence_start = dayjs(r.silence_start, 'HH:mm:ss');
            if (r.silence_end) vals.silence_end = dayjs(r.silence_end, 'HH:mm:ss');
            form.setFieldsValue(vals);
            loadDbList();
            setRuleModalOpen(true);
          }}>{t('common.edit')}</Button>
          {!r.is_builtin && <Button type="link" size="small" danger onClick={() => handleRuleDelete(r.id)}>{t('common.delete')}</Button>}
        </Space>
      ),
    },
  ];

  return (
    <div>
      {contextHolder}
      <PageHeader title={t('alerts.title')} />
      <Tabs defaultActiveKey="alerts" onChange={k => { if (k === 'rules') fetchRules(); }} items={[
        {
          key: 'alerts', label: t('alerts.alertList'),
          children: (
            <>
              <Row style={{ marginBottom: 16 }}>
                <Col span={24}>
                  <Space wrap size="middle">
                    <Select
                      placeholder={t('alerts.filterStatus')}
                      allowClear
                      style={{ width: isMobile ? '100%' : 120, minWidth: isMobile ? 140 : 120 }}
                      onChange={v => { setStatusFilter(v || ''); setPage(1); }}
                      options={[
                        { label: t('alerts.statusTypes.firing'), value: 'firing' },
                        { label: t('alerts.statusTypes.resolved'), value: 'resolved' },
                        { label: t('alerts.statusTypes.acknowledged'), value: 'acknowledged' }
                      ]}
                    />
                    <Select
                      placeholder={t('alerts.filterLevel')}
                      allowClear
                      style={{ width: isMobile ? '100%' : 120, minWidth: isMobile ? 140 : 120 }}
                      onChange={v => { setSeverityFilter(v || ''); setPage(1); }}
                      options={[
                        { label: t('alerts.severityLevels.critical'), value: 'critical' },
                        { label: t('alerts.severityLevels.warning'), value: 'warning' },
                        { label: t('alerts.severityLevels.info'), value: 'info' }
                      ]}
                    />
                  </Space>
                </Col>
              </Row>
              <Card>
                {loadError ? (
                  <ErrorState error={loadError} onRetry={fetchAlerts} />
                ) : (
                  <Table
                    dataSource={alerts}
                    columns={isMobile ? mobileAlertColumns : alertColumns}
                    rowKey="id"
                    loading={loading}
                    size="small"
                    pagination={{
                      current: page,
                      pageSize: 25,
                      total,
                      onChange: p => setPage(p),
                      showSizeChanger: !isMobile,
                      showQuickJumper: !isMobile,
                      simple: isMobile,
                      pageSizeOptions: ['25', '50', '100'],
                    }}
                    scroll={isMobile ? { x: 'max-content' } : undefined}
                    locale={{ emptyText: (
                      <Empty description={t('alerts.noAlerts')} image={Empty.PRESENTED_IMAGE_SIMPLE}>
                        <span style={{ color: '#52c41a', display: 'block', marginBottom: 8 }}>🎉 {t('alerts.systemNormal')}</span>
                        <Button type="primary" onClick={() => { fetchRules(); }}>
                          {t('alerts.configureRules')}
                        </Button>
                      </Empty>
                    ) }}
                  />
                )}
              </Card>
            </>
          ),
        },
        {
          key: 'rules', label: t('alerts.alertRules'),
          children: (
            <>
              <Row justify="end" style={{ marginBottom: 16 }}>
                <Button type="primary" onClick={() => { setEditingRule(null); setRuleType('metric'); form.resetFields(); setRuleModalOpen(true); loadDbList(); }}>{t('alerts.createRule')}</Button>
              </Row>
              <Card>
                <Table dataSource={rules} columns={ruleColumns} rowKey="id" loading={rulesLoading} pagination={false} />
              </Card>
            </>
          ),
        },
        {
          key: 'noise-reduction', label: `🔇 ${t('alerts.noiseReduction')}`,
          children: <NoiseReduction />,
        },
      ]} />

      {/* 告警详情抽屉 */}
      <Drawer
        open={!!selectedAlert}
        onClose={() => { setSelectedAlert(null); setDrawerAiResult(null); }}
        title={t('alerts.alertInfo')}
        width={isMobile ? '100%' : 480}
      >
        {selectedAlert && (
          <>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label={t('alerts.title_field')}>{getAlertTitle(selectedAlert)}</Descriptions.Item>
              <Descriptions.Item label={t('alerts.message_field')}>{selectedAlert.message}</Descriptions.Item>
              <Descriptions.Item label={t('alerts.severity')}><Tag color={severityColor[selectedAlert.severity]}>{selectedAlert.severity}</Tag></Descriptions.Item>
              <Descriptions.Item label={t('alerts.status')}><Tag color={statusColor[selectedAlert.status]}>{selectedAlert.status}</Tag></Descriptions.Item>
              <Descriptions.Item label={t('alerts.triggeredAt')}>{new Date(selectedAlert.fired_at).toLocaleString()}</Descriptions.Item>
              <Descriptions.Item label={t('alerts.resolvedAt')}>{selectedAlert.resolved_at ? new Date(selectedAlert.resolved_at).toLocaleString() : '-'}</Descriptions.Item>
              <Descriptions.Item label={t('alerts.acknowledgedAt')}>{selectedAlert.acknowledged_at ? new Date(selectedAlert.acknowledged_at).toLocaleString() : '-'}</Descriptions.Item>
            </Descriptions>
            <Space style={{ marginTop: 16 }}>
              {selectedAlert.status === 'firing' && (
                <Button type="primary" onClick={() => handleAck(selectedAlert.id)}>{t('alerts.acknowledgeAlert')}</Button>
              )}
              {isRuleSilenced(selectedAlert) ? (
                <Button
                  icon={<PlayCircleOutlined />}
                  onClick={() => handleLiftSilence(selectedAlert.rule_id)}
                >
                  {t('alertSilence.liftSilence')}
                </Button>
              ) : (
                <Button
                  icon={<PauseCircleOutlined />}
                  onClick={() => { setSelectedAlert(null); openSilenceModal(selectedAlert); }}
                >
                  {t('alertSilence.silence')}
                </Button>
              )}
            </Space>
            <Collapse
              style={{ marginTop: 16 }}
              items={[{
                key: 'ai',
                label: (
                  <Space>
                    <span>🤖 {t('alerts.rootCauseTitle')}</span>
                    <Button
                      size="small"
                      type="primary"
                      onClick={e => { e.stopPropagation(); handleDrawerAiAnalyze(selectedAlert.id); }}
                      loading={drawerAiLoading}
                      disabled={drawerAiLoading}
                    >
                      {t('alerts.analyzeNow')}
                    </Button>
                  </Space>
                ),
                children: drawerAiLoading ? (
                  <div style={{ textAlign: 'center', padding: 24 }}><Spin tip={t('alerts.aiSpinTip')} /></div>
                ) : drawerAiResult ? (
                  <Typography.Text>{drawerAiResult}</Typography.Text>
                ) : (
                  <Typography.Text type="secondary">{t('alerts.clickToAnalyze')}</Typography.Text>
                ),
              }]}
            />
          </>
        )}
      </Drawer>

      {/* 告警规则编辑弹窗 */}
      <Modal title={editingRule ? t('alerts.editRule') : t('alerts.newRule')} open={ruleModalOpen} onCancel={() => setRuleModalOpen(false)}
        onOk={() => form.submit()} destroyOnClose width={isMobile ? '100%' : 560}>
        <Form form={form} layout="vertical" onFinish={handleRuleSave} initialValues={{ rule_type: 'metric' }}>
          <Form.Item name="name" label={t('alerts.rules.name')} rules={[{ required: true }]}><Input /></Form.Item>
          <Form.Item name="rule_type" label={t('alerts.rules.type')} rules={[{ required: true }]}>
            <Select onChange={(v: string) => setRuleType(v)} options={[
              { label: t('alerts.rules.metric'), value: 'metric' },
              { label: t('alerts.rules.logKeyword'), value: 'log_keyword' },
              { label: t('alerts.rules.database'), value: 'db_metric' },
            ]} />
          </Form.Item>

          {ruleType === 'metric' && (
            <Form.Item name="metric" label={t('alerts.rules.metric')} rules={[{ required: true }]}>
              <Select options={[
                { label: t('alerts.rules.metricCpu'), value: 'cpu_percent' },
                { label: t('alerts.rules.metricMemory'), value: 'memory_percent' },
                { label: t('alerts.rules.metricDisk'), value: 'disk_percent' },
              ]} />
            </Form.Item>
          )}

          {ruleType === 'log_keyword' && (
            <>
              <Form.Item name="log_keyword" label={t('alerts.rules.matchKeyword')} rules={[{ required: true }]}><Input placeholder="e.g.: ERROR, OutOfMemory" /></Form.Item>
              <Form.Item name="log_level" label={t('alerts.rules.logLevel')}>
                <Select allowClear options={[
                  { label: 'DEBUG', value: 'DEBUG' }, { label: 'INFO', value: 'INFO' },
                  { label: 'WARN', value: 'WARN' }, { label: 'ERROR', value: 'ERROR' }, { label: 'FATAL', value: 'FATAL' },
                ]} />
              </Form.Item>
              <Form.Item name="log_service" label={t('alerts.rules.logService')}><Input placeholder="e.g.: nginx, app" /></Form.Item>
            </>
          )}

          {ruleType === 'db_metric' && (
            <>
              <Form.Item name="db_id" label={t('alerts.rules.dbEmpty')}>
                <Select allowClear options={dbList.map(d => ({ label: `${d.name} (${d.db_type})`, value: d.id }))} />
              </Form.Item>
              <Form.Item name="db_metric_name" label={t('alerts.rules.dbMetric')} rules={[{ required: true }]}>
                <Select options={[
                  { label: t('alerts.rules.dbConnections'), value: 'connections_total' },
                  { label: t('alerts.rules.dbActiveConnections'), value: 'connections_active' },
                  { label: t('alerts.rules.dbSlowQueries'), value: 'slow_queries' },
                  { label: t('alerts.rules.dbSize'), value: 'database_size_mb' },
                  { label: 'QPS', value: 'qps' },
                ]} />
              </Form.Item>
            </>
          )}

          {(ruleType === 'metric' || ruleType === 'db_metric') && (
            <>
              <Form.Item name="operator" label={t('alerts.rules.operator')} rules={[{ required: true }]}>
                <Select options={[{ label: '>', value: '>' }, { label: '>=', value: '>=' }, { label: '<', value: '<' }, { label: '<=', value: '<=' }]} />
              </Form.Item>
              <Form.Item name="threshold" label={t('alerts.rules.threshold')} rules={[{ required: true }]}><InputNumber style={{ width: '100%' }} /></Form.Item>
            </>
          )}

          <Form.Item name="duration_seconds" label={t('alerts.rules.durationSeconds')}><InputNumber style={{ width: '100%' }} /></Form.Item>
          <Form.Item name="severity" label={t('alerts.severity')} rules={[{ required: true }]}>
            <Select options={[
              { label: t('alerts.severityLevels.critical'), value: 'critical' },
              { label: t('alerts.severityLevels.warning'), value: 'warning' },
              { label: t('alerts.severityLevels.info'), value: 'info' }
            ]} />
          </Form.Item>
          <Form.Item name="is_enabled" label={t('alerts.rules.enabled')} valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="cooldown_seconds" label={t('alerts.rules.cooldown')} initialValue={300}>
            <InputNumber style={{ width: '100%' }} min={0} />
          </Form.Item>
          <Form.Item name="silence_start" label={t('alerts.rules.silenceStart')}>
            <TimePicker format="HH:mm" style={{ width: '100%' }} />
          </Form.Item>
          <Form.Item name="silence_end" label={t('alerts.rules.silenceEnd')}>
            <TimePicker format="HH:mm" style={{ width: '100%' }} />
          </Form.Item>
        </Form>
      </Modal>

      {/* AI 根因分析弹窗 */}
      <Modal title={<><RobotOutlined /> {t('alerts.rootCauseTitle')}</>} open={rcModalOpen} onCancel={() => setRcModalOpen(false)} footer={null} width={560}>
        {rcLoading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><Spin tip={t('alerts.analyzing')} /></div>
        ) : rcData ? (
          <div>
            <Descriptions column={1} bordered size="small">
              <Descriptions.Item label={t('alerts.rootCause')}>{rcData.root_cause}</Descriptions.Item>
              <Descriptions.Item label={t('alerts.confidence')}>
                <Tag color={rcData.confidence === 'high' ? 'green' : rcData.confidence === 'medium' ? 'orange' : 'default'}>
                  {rcData.confidence}
                </Tag>
              </Descriptions.Item>
            </Descriptions>
            {rcData.evidence && rcData.evidence.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <Typography.Text strong>{t('alerts.evidence')}</Typography.Text>
                <ul style={{ marginTop: 8 }}>{rcData.evidence.map((e, i) => <li key={i}>{e}</li>)}</ul>
              </div>
            )}
            {rcData.recommendations && rcData.recommendations.length > 0 && (
              <div style={{ marginTop: 16 }}>
                <Typography.Text strong>{t('alerts.recommendations')}</Typography.Text>
                <ul style={{ marginTop: 8 }}>{rcData.recommendations.map((r, i) => <li key={i}>{r}</li>)}</ul>
              </div>
            )}
          </div>
        ) : null}
      </Modal>

      {/* 告警静默 Modal */}
      <Modal
        title={<><PauseCircleOutlined /> {t('alertSilence.title')}</>}
        open={silenceModalOpen}
        onCancel={() => setSilenceModalOpen(false)}
        onOk={handleSilence}
        okText={t('alertSilence.silence')}
        confirmLoading={silenceLoading}
        width={420}
      >
        {silenceTarget && (
          <div>
            <Typography.Text type="secondary" style={{ display: 'block', marginBottom: 16 }}>
              {t('alertSilence.description')}
            </Typography.Text>
            <Typography.Text strong style={{ display: 'block', marginBottom: 12 }}>
              {t('alertSilence.duration')}
            </Typography.Text>
            <Radio.Group
              value={silenceDuration}
              onChange={e => setSilenceDuration(e.target.value)}
              style={{ display: 'flex', flexDirection: 'column', gap: 8 }}
            >
              <Radio value={1}>{t('alertSilence.oneHour')}</Radio>
              <Radio value={4}>{t('alertSilence.fourHours')}</Radio>
              <Radio value={24}>{t('alertSilence.twentyFourHours')}</Radio>
              <Radio value={-1}>
                <Space>
                  {t('alertSilence.custom')}
                  {silenceDuration === -1 && (
                    <InputNumber
                      min={1}
                      max={720}
                      value={silenceCustomHours}
                      onChange={v => setSilenceCustomHours(v || 1)}
                      placeholder={t('alertSilence.customPlaceholder')}
                      addonAfter={t('common.minute').replace('分钟', '小时')}
                      style={{ width: 140 }}
                    />
                  )}
                </Space>
              </Radio>
            </Radio.Group>
          </div>
        )}
      </Modal>
    </div>
  );
}
