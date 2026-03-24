/**
 * 数据库监控列表页面
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Tag, Typography, Spin, Button, Card, Space, Modal, Form, Input, Select, InputNumber, Switch, Popconfirm, message } from 'antd';
import { useTranslation } from 'react-i18next';
import { databaseService } from '../services/databases';
import type { DatabaseItem, DatabaseTargetItem, DatabaseTargetPayload } from '../services/databases';
import { hostService } from '../services/hosts';
import PageHeader from '../components/PageHeader';

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
  const [targets, setTargets] = useState<DatabaseTargetItem[]>([]);
  const [hostOptions, setHostOptions] = useState<Array<{ label: string; value: number }>>([]);
  const [loading, setLoading] = useState(true);
  const [targetLoading, setTargetLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTarget, setEditingTarget] = useState<DatabaseTargetItem | null>(null);
  const [saving, setSaving] = useState(false);
  const [messageApi, contextHolder] = message.useMessage();
  const [form] = Form.useForm<DatabaseTargetPayload>();
  const navigate = useNavigate();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const { data } = await databaseService.list();
        setDatabases(data.databases || []);
      } catch (err) { console.warn('Failed to fetch databases:', err); } finally { setLoading(false); }
    };
    const fetchTargets = async () => {
      setTargetLoading(true);
      try {
        const { data } = await databaseService.listTargets();
        setTargets(data.items || []);
      } catch {
        // 非管理员访问会 403，这里静默降级
      } finally {
        setTargetLoading(false);
      }
    };
    const fetchHosts = async () => {
      try {
        const allHosts: Array<{ id: string | number; hostname: string; display_name?: string | null }> = [];
        let page = 1;
        const pageSize = 100;
        while (true) {
          const { data } = await hostService.list({ page, page_size: pageSize });
          const items = data.items || [];
          allHosts.push(...items);
          if (items.length < pageSize) break;
          page += 1;
        }
        const options = allHosts.map((h) => ({
          value: Number(h.id),
          label: `${h.display_name || h.hostname} (#${h.id})`,
        }));
        setHostOptions(options);
      } catch {
        // ignore
      }
    };
    fetchData();
    fetchTargets();
    fetchHosts();
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

  const targetColumns = [
    { title: t('databases.name'), dataIndex: 'name', key: 'name' },
    { title: t('databases.host'), dataIndex: 'host_name', key: 'host_name' },
    {
      title: t('databases.type'),
      dataIndex: 'db_type',
      key: 'db_type',
      render: (v: string) => v === 'postgres' ? 'PostgreSQL' : v === 'mysql' ? 'MySQL' : v === 'oracle' ? 'Oracle' : v === 'redis' ? 'Redis' : v,
    },
    { title: 'Endpoint', key: 'endpoint', render: (_: unknown, r: DatabaseTargetItem) => `${r.db_host}:${r.db_port}/${r.db_name || '-'}` },
    { title: 'Interval(s)', dataIndex: 'interval_sec', key: 'interval_sec' },
    {
      title: t('databases.status'),
      key: 'is_active',
      render: (_: unknown, r: DatabaseTargetItem) => (
        <Switch
          checked={r.is_active}
          onChange={async (checked) => {
            try {
              await databaseService.updateTarget(r.id, { is_active: checked });
              setTargets((prev) => prev.map((x) => (x.id === r.id ? { ...x, is_active: checked } : x)));
            } catch {
              messageApi.error(t('common.failed'));
            }
          }}
        />
      ),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      render: (_: unknown, r: DatabaseTargetItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            onClick={() => {
              setEditingTarget(r);
              form.setFieldsValue({
                host_id: r.host_id,
                name: r.name,
                db_type: r.db_type,
                db_host: r.db_host,
                db_port: r.db_port,
                db_name: r.db_name,
                username: r.username,
                password: '',
                interval_sec: r.interval_sec,
                connect_timeout_sec: r.connect_timeout_sec,
                is_active: r.is_active,
              });
              setModalOpen(true);
            }}
          >
            {t('common.edit')}
          </Button>
          <Popconfirm
            title={t('common.delete')}
            description={t('databases.deleteTargetConfirm')}
            onConfirm={async () => {
              try {
                await databaseService.deleteTarget(r.id);
                setTargets((prev) => prev.filter((x) => x.id !== r.id));
                messageApi.success(t('common.success'));
              } catch {
                messageApi.error(t('common.failed'));
              }
            }}
          >
            <Button type="link" danger size="small">{t('common.delete')}</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const openCreateModal = () => {
    setEditingTarget(null);
    form.resetFields();
    form.setFieldsValue({
      db_type: 'postgres',
      db_host: '127.0.0.1',
      db_port: 5432,
      interval_sec: 60,
      connect_timeout_sec: 10,
      is_active: true,
      username: '',
      password: '',
      db_name: '',
      name: '',
      host_id: hostOptions[0]?.value,
    });
    setModalOpen(true);
  };

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editingTarget) {
        const payload: Partial<DatabaseTargetPayload> = { ...values };
        if (!payload.password) {
          delete payload.password;
        }
        await databaseService.updateTarget(editingTarget.id, payload);
      } else {
        await databaseService.createTarget(values);
      }
      const { data } = await databaseService.listTargets();
      setTargets(data.items || []);
      setModalOpen(false);
      messageApi.success(t('common.success'));
    } catch {
      // ignore
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      {contextHolder}
      <PageHeader title={t('databases.title')} />

      <Card
        title={t('databases.targetConfigTitle')}
        extra={<Button type="primary" onClick={openCreateModal}>{t('databases.addTarget')}</Button>}
        style={{ marginBottom: 16 }}
      >
        <Table
          dataSource={targets}
          columns={targetColumns}
          rowKey="id"
          size="small"
          loading={targetLoading}
          pagination={false}
        />
      </Card>

      <Typography.Title level={5}>{t('databases.runtimeMetricsTitle')}</Typography.Title>
      <Table
        dataSource={databases}
        columns={columns}
        rowKey="id"
        size="small"
        pagination={false}
        onRow={(record) => ({ onClick: () => navigate(`/databases/${record.id}`), style: { cursor: 'pointer' } })}
      />

      <Modal
        title={editingTarget ? t('databases.editTarget') : t('databases.addTarget')}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={handleSubmit}
        confirmLoading={saving}
      >
        <Form form={form} layout="vertical">
          <Form.Item name="host_id" label={t('databases.targetHost')} rules={[{ required: true }]}>
            <Select options={hostOptions} />
          </Form.Item>
          <Form.Item name="name" label={t('databases.name')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="db_type" label={t('databases.type')} rules={[{ required: true }]}>
            <Select
              options={[
                { label: 'PostgreSQL', value: 'postgres' },
                { label: 'MySQL', value: 'mysql' },
                { label: 'Oracle', value: 'oracle' },
                { label: 'Redis', value: 'redis' },
              ]}
              onChange={(v) => {
                const portMap: Record<string, number> = { postgres: 5432, mysql: 3306, oracle: 1521, redis: 6379 };
                form.setFieldValue('db_port', portMap[v] || 5432);
              }}
            />
          </Form.Item>
          <Form.Item name="db_host" label={t('databases.host')} rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item name="db_port" label={t('databases.port')} rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={65535} />
          </Form.Item>
          <Form.Item name="db_name" label={t('databases.dbName')}>
            <Input />
          </Form.Item>
          <Form.Item name="username" label={t('databases.username')}>
            <Input />
          </Form.Item>
          <Form.Item name="password" label={t('databases.password')}>
            <Input.Password placeholder={editingTarget ? t('databases.passwordPlaceholder') : ''} />
          </Form.Item>
          <Form.Item name="interval_sec" label={t('databases.collectInterval')} rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={15} max={3600} />
          </Form.Item>
          <Form.Item name="connect_timeout_sec" label={t('databases.connectTimeout')} rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={1} max={120} />
          </Form.Item>
          <Form.Item name="is_active" label={t('databases.status')} valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
