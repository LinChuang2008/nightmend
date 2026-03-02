/**
 * 最新告警列表组件
 */
import { Card, Table, Tag } from 'antd';
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
}

export default function AlertsList({ alerts }: AlertsListProps) {
  const { t } = useTranslation();

  const severityColor: Record<string, string> = { 
    critical: 'red', 
    warning: 'orange', 
    info: 'blue' 
  };

  const columns = [
    { 
      title: t('dashboard.alertTitle'), 
      dataIndex: 'title', 
      key: 'title' 
    },
    { 
      title: t('dashboard.alertSeverity'), 
      dataIndex: 'severity', 
      key: 'severity',
      render: (severity: string) => (
        <Tag color={severityColor[severity] || 'default'}>
          {severity}
        </Tag>
      )
    },
    { 
      title: t('dashboard.alertFiredAt'), 
      dataIndex: 'fired_at', 
      key: 'fired_at',
      render: (time: string) => new Date(time).toLocaleString()
    },
  ];

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
    </Card>
  );
}
