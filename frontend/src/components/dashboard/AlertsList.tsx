/**
 * 最新告警列表组件
 * 无告警时，若存在 FATAL/ERROR 日志则显示联动告警 Banner
 */
import { Card, Table, Tag, Alert, Button, Space } from 'antd';
import { WarningFilled } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

interface AlertItem {
  id: string;
  title: string;
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

export default function AlertsList({
  alerts,
  fatalCount = 0,
  errorCount = 0,
  onAIAnalyze,
  onViewLogs,
}: AlertsListProps) {
  const { t } = useTranslation();

  const severityColor: Record<string, string> = {
    critical: 'red',
    warning: 'orange',
    info: 'blue',
  };

  const columns = [
    {
      title: t('dashboard.alertTitle'),
      dataIndex: 'title',
      key: 'title',
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
            background: '#fffbe6',
            border: '1px solid #ffe58f',
            borderRadius: 6,
          }}
          type="warning"
          showIcon
          icon={<WarningFilled style={{ color: '#faad14' }} />}
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
}
