import { useEffect, useState } from 'react';
import { Table, Row, Col, Typography, Select, Space, message, Tag, Tooltip } from 'antd';
import dayjs from 'dayjs';
import { useTranslation } from 'react-i18next';

import { fetchAIOperationLogs, type AIOperationLogItem } from '../services/aiOperationLogs';
import { fetchUsers } from '../services/users';

const { Title } = Typography;

export default function AIOperationLogs() {
  const { t } = useTranslation();
  const [messageApi, contextHolder] = message.useMessage();
  const [items, setItems] = useState<AIOperationLogItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string | undefined>();
  const [userFilter, setUserFilter] = useState<number | undefined>();
  const [userOptions, setUserOptions] = useState<{ label: string; value: number }[]>([]);

  const loadUsers = async () => {
    try {
      const { data } = await fetchUsers(1, 100);
      setUserOptions((data.items || []).map((u) => ({ label: u.name || u.email, value: u.id })));
    } catch {
      // ignore user filter loading failures
    }
  };

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await fetchAIOperationLogs({
        page,
        page_size: pageSize,
        status: statusFilter,
        user_id: userFilter,
      });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch {
      messageApi.error(t('aiOperationLogs.loadFailed'));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadUsers();
  }, []);

  useEffect(() => {
    load();
  }, [page, statusFilter, userFilter]);

  const columns = [
    {
      title: t('aiOperationLogs.time'),
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => dayjs(v).format('YYYY-MM-DD HH:mm:ss'),
    },
    { title: t('aiOperationLogs.user'), dataIndex: 'user_name', key: 'user_name', width: 140 },
    {
      title: t('aiOperationLogs.host'),
      dataIndex: 'host_name',
      key: 'host_name',
      width: 180,
      render: (_: string, row: AIOperationLogItem) => row.host_name || (row.host_id ? `host-${row.host_id}` : '-'),
    },
    {
      title: t('aiOperationLogs.command'),
      dataIndex: 'command',
      key: 'command',
      ellipsis: true,
      render: (cmd: string) => (
        <Tooltip title={<pre style={{ margin: 0, maxHeight: 300, overflow: 'auto' }}>{cmd}</pre>}>
          <span style={{ cursor: 'pointer' }}>{cmd}</span>
        </Tooltip>
      ),
    },
    {
      title: t('aiOperationLogs.status'),
      dataIndex: 'status',
      key: 'status',
      width: 120,
      render: (status: string) => (
        <Tag color={status === 'success' ? 'green' : status === 'failed' ? 'red' : 'default'}>
          {status}
        </Tag>
      ),
    },
    { title: t('aiOperationLogs.exitCode'), dataIndex: 'exit_code', key: 'exit_code', width: 100, render: (v: number | null) => v ?? '-' },
    {
      title: t('aiOperationLogs.duration'),
      dataIndex: 'duration_ms',
      key: 'duration_ms',
      width: 120,
      render: (v: number | null) => (typeof v === 'number' ? `${v} ms` : '-'),
    },
    {
      title: t('aiOperationLogs.reason'),
      dataIndex: 'reason',
      key: 'reason',
      width: 220,
      ellipsis: true,
      render: (v: string | null) => v || '-',
    },
  ];

  return (
    <>
      {contextHolder}
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Title level={4} style={{ margin: 0 }}>{t('aiOperationLogs.title')}</Title>
        </Col>
        <Col>
          <Space>
            <Select
              allowClear
              placeholder={t('aiOperationLogs.filterStatus')}
              style={{ width: 160 }}
              options={[
                { label: t('aiOperationLogs.statusSuccess'), value: 'success' },
                { label: t('aiOperationLogs.statusFailed'), value: 'failed' },
              ]}
              value={statusFilter}
              onChange={(v) => { setStatusFilter(v); setPage(1); }}
            />
            <Select
              allowClear
              showSearch
              optionFilterProp="label"
              placeholder={t('aiOperationLogs.filterUser')}
              style={{ width: 180 }}
              options={userOptions}
              value={userFilter}
              onChange={(v) => { setUserFilter(v); setPage(1); }}
            />
          </Space>
        </Col>
      </Row>
      <Table
        rowKey="id"
        columns={columns}
        dataSource={items}
        loading={loading}
        pagination={{
          current: page,
          pageSize,
          total,
          onChange: (p) => setPage(p),
          showTotal: (count) => t('common.total', { count }),
        }}
      />
    </>
  );
}

