/**
 * 数据库监控列表页面
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tag, Typography, Spin } from 'antd';
import { useTranslation } from 'react-i18next';
import { databaseService } from '../services/databases';
import type { DatabaseItem } from '../services/databases';

const statusColor: Record<string, string> = {
  healthy: 'success',
  warning: 'warning',
  critical: 'error',
  unknown: 'default',
};

const dbTypeIcon: Record<string, string> = {
  postgres: '🐘',
  postgresql: '🐘',
  mysql: '🐬',
  oracle: '🔴',
};

export default function Databases() {
  const { t } = useTranslation();
  const [databases, setDatabases] = useState<DatabaseItem[]>([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const { data } = await databaseService.list();
        setDatabases(data.databases || []);
      } catch (err) { console.warn('Failed to fetch databases:', err); } finally { setLoading(false); }
    };
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  const columns = [
    {
      title: t('databases.name'), dataIndex: 'name', key: 'name',
      render: (name: string, record: DatabaseItem) => (
        <span>{dbTypeIcon[record.db_type] || '🗄️'} {name}</span>
      ),
    },
    {
      title: t('databases.type'), dataIndex: 'db_type', key: 'db_type',
      render: (val: string) => val === 'postgres' || val === 'postgresql' ? 'PostgreSQL' : val === 'mysql' ? 'MySQL' : val === 'oracle' ? 'Oracle' : val,
    },
    {
      title: t('databases.status'), dataIndex: 'status', key: 'status',
      render: (s: string) => <Tag color={statusColor[s] || 'default'}>{s}</Tag>,
    },
    {
      title: t('databases.connections'), key: 'connections',
      render: (_: unknown, r: DatabaseItem) => r.latest_metrics?.connections_total ?? '-',
    },
    {
      title: t('databases.size'), key: 'size',
      render: (_: unknown, r: DatabaseItem) => r.latest_metrics?.database_size_mb?.toFixed(1) ?? '-',
    },
    {
      title: t('databases.slowQueries'), key: 'slow',
      render: (_: unknown, r: DatabaseItem) => {
        const v = r.latest_metrics?.slow_queries;
        if (v == null) return '-';
        return v > 0 ? <Tag color="warning">{v}</Tag> : <Tag color="success">{v}</Tag>;
      },
    },
    {
      title: 'QPS', key: 'qps',
      render: (_: unknown, r: DatabaseItem) => r.latest_metrics?.qps?.toFixed(1) ?? '-',
    },
    {
      title: t('databases.tablespace'), key: 'tablespace',
      render: (_: unknown, r: DatabaseItem) => {
        if (r.db_type !== 'oracle') return '-';
        const v = r.latest_metrics?.tablespace_used_pct;
        if (v == null) return '-';
        return v > 90 ? <Tag color="error">{v.toFixed(1)}%</Tag> : v > 75 ? <Tag color="warning">{v.toFixed(1)}%</Tag> : `${v.toFixed(1)}%`;
      },
    },
  ];

  return (
    <div>
      <Typography.Title level={4}>{t('databases.title')}</Typography.Title>
      <Table
        dataSource={databases}
        columns={columns}
        rowKey="id"
        size="small"
        pagination={false}
        onRow={(record) => ({ onClick: () => navigate(`/databases/${record.id}`), style: { cursor: 'pointer' } })}
      />
    </div>
  );
}
