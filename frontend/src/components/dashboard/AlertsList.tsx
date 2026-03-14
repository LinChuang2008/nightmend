/**
 * 最新告警列表组件
 * 无告警时，若存在 FATAL/ERROR 日志则显示联动告警 Banner
 */
import { memo } from 'react';
import { Card, Table, Tag, Alert, Button, Space, theme } from 'antd';
import { WarningFilled } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface AlertItem {
  id: string;
  title: string;
  title_en?: string | null;
  severity: string;
  status: string;
  fired_at: string;
}

interface AlertsListProps {
  alerts: AlertItem[];
  fatalCount?: number;
  errorCount?: number;
  onAIAnalyze?: () => void;
  onViewLogs?: () => void;
}

export default memo(function AlertsList({
  alerts,
  fatalCount = 0,
  errorCount = 0,
  onAIAnalyze,
  onViewLogs,
}: AlertsListProps) {
  const { t, i18n } = useTranslation();
  const { token } = theme.useToken();
  const getAlertTitle = (alert: AlertItem) =>
    i18n.language === 'en' && alert.title_en ? alert.title_en : alert.title;

  const severityColor: Record<string, string> = {
    critical: 'red',
    warning: 'orange',
    info: 'blue',
  };

  const columns = [
    {
      title: t('dashboard.alertTitle'),
      key: 'title',
      render: (_: unknown, record: AlertItem) => getAlertTitle(record),
    },
    {
      title: t('dashboard.alertSeverity'),
      dataIndex: 'severity',
      key: 'severity',
      render: (severity: string) => (
        <Tag color={severityColor[severity] || 'default'}>{severity}</Tag>
      ),
    },
    {
      title: t('dashboard.alertFiredAt'),
      dataIndex: 'fired_at',
      key: 'fired_at',
      render: (time: string) => new Date(time).toLocaleString(),
    },
  ];

  const hasAbnormalLogs = fatalCount > 0 || errorCount > 0;

  // 构造联动消息
  const logAlertParts: string[] = [];
  if (fatalCount > 0) logAlertParts.push(`FATAL×${fatalCount}`);
  if (errorCount > 0) logAlertParts.push(`ERROR×${errorCount}`);
  const logAlertMsg = t('dashboard.alertsLogLinkedMsg', {
    counts: logAlertParts.join(' / '),
  });

  return (
    <Card title={t('dashboard.recentAlertsTitle')}>
      <Table
        dataSource={alerts}
        rowKey="id"
        columns={columns}
        pagination={false}
        size="small"
        locale={{ emptyText: t('dashboard.noActiveAlerts') }}
      />

      {/* 无告警但有 FATAL/ERROR 日志时显示联动 Banner */}
      {alerts.length === 0 && hasAbnormalLogs && (
        <Alert
          style={{
            marginTop: 12,
            background: token.colorWarningBg,
            border: `1px solid ${token.colorWarningBorder}`,
            borderRadius: 6,
          }}
          type="warning"
          showIcon
          icon={<WarningFilled style={{ color: token.colorWarning }} />}
          message={logAlertMsg}
          description={t('dashboard.alertsLogLinkedDesc')}
          action={
            <Space direction="vertical" size={4}>
              <Button size="small" type="primary" onClick={onAIAnalyze}>
                {t('dashboard.viewAIAnalysis')}
              </Button>
              <Button size="small" onClick={onViewLogs}>
                {t('dashboard.viewLogsPage')}
              </Button>
            </Space>
          }
        />
      )}
    </Card>
  );
})
