/**
 * 服务组视图页 (Service Groups Page)
 *
 * 功能：跨主机同名服务归组展示，从服务维度（而非服务器维度）观察系统
 * 数据源：GET /api/v1/topology/service-groups (服务组列表 + 实例分布)
 *
 * 页面结构：
 *   1. 统计卡片行 - 服务组总数、健康/异常/告警数量
 *   2. 搜索栏 - 按服务名搜索
 *   3. 服务组表格 - 服务名、类型、实例数、分布服务器、整体状态
 *      展开行 → 显示该服务在各服务器上的实例详情
 *
 * 使用场景：快速定位某个服务（如 Redis、Nginx）在哪些服务器上运行及其健康状态
 */
import { useEffect, useState, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Typography, Table, Tag, Card, Space, Button, Input, message, Badge, Empty, Row, Col, Statistic,
} from 'antd';
import {
  ArrowLeftOutlined, ReloadOutlined, SearchOutlined, AppstoreOutlined,
  CloudServerOutlined, CheckCircleOutlined,
} from '@ant-design/icons';
import api from '../../services/api';

const { Title, Text } = Typography;

interface ServerInstance {
  server_id: number;
  hostname: string;
  ip_address: string | null;
  server_status: string;
  port: number | null;
  pid: number | null;
  service_status: string;
  cpu_percent: number;
  mem_mb: number;
}

interface ServiceGroupData {
  id: number;
  name: string;
  category: string | null;
  created_at: string | null;
  server_count: number;
  servers: ServerInstance[];
}

const categoryConfig: Record<string, { color: string; label: string }> = {
  web: { color: 'orange', label: '前端/Web' },
  db: { color: 'purple', label: '数据库' },
  cache: { color: 'green', label: '缓存' },
  app: { color: 'blue', label: '应用' },
  mq: { color: 'cyan', label: '消息队列' },
  api: { color: 'red', label: 'API' },
  other: { color: 'default', label: '其他' },
};

const svcStatusTag = (s: string) => {
  const map: Record<string, string> = { running: 'success', stopped: 'error', error: 'warning' };
  return <Tag color={map[s] || 'default'}>{s}</Tag>;
};

export default function ServiceGroupsPage() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [groups, setGroups] = useState<ServiceGroupData[]>([]);
  const [search, setSearch] = useState('');

  const fetchGroups = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/topology/service-groups');
      setGroups(data);
    } catch {
      message.error('加载服务组失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchGroups(); }, [fetchGroups]);

  const filtered = groups.filter(g =>
    !search ||
    g.name.toLowerCase().includes(search.toLowerCase()) ||
    g.category?.toLowerCase().includes(search.toLowerCase())
  );

  const totalInstances = groups.reduce((sum, g) => sum + g.server_count, 0);

  const columns = [
    {
      title: '服务组',
      dataIndex: 'name',
      sorter: (a: ServiceGroupData, b: ServiceGroupData) => a.name.localeCompare(b.name),
      render: (text: string) => <Text strong>{text}</Text>,
    },
    {
      title: '分类',
      dataIndex: 'category',
      sorter: (a: ServiceGroupData, b: ServiceGroupData) => (a.category || '').localeCompare(b.category || ''),
      filters: Object.entries(categoryConfig).map(([k, v]) => ({ text: v.label, value: k })),
      onFilter: (value: any, record: ServiceGroupData) => record.category === value,
      render: (v: string | null) => {
        if (!v) return '—';
        const cfg = categoryConfig[v] || categoryConfig.other;
        return <Tag color={cfg.color}>{cfg.label}</Tag>;
      },
    },
    {
      title: '服务器数',
      dataIndex: 'server_count',
      sorter: (a: ServiceGroupData, b: ServiceGroupData) => a.server_count - b.server_count,
      render: (v: number) => <Badge count={v} showZero style={{ backgroundColor: v > 0 ? '#10B981' : '#d9d9d9' }} />,
    },
  ];

  const expandedRowRender = (record: ServiceGroupData) => {
    if (record.servers.length === 0) return <Empty description="无运行实例" />;
    return (
      <Table
        rowKey={(r) => `${r.server_id}-${r.port}`}
        dataSource={record.servers}
        pagination={false}
        size="small"
        columns={[
          {
            title: '主机名', dataIndex: 'hostname',
            render: (text: string, r: ServerInstance) => (
              <a onClick={() => navigate(`/topology/servers/${r.server_id}`)}>{text}</a>
            ),
          },
          { title: 'IP', dataIndex: 'ip_address', render: (v: string | null) => v || '—' },
          { title: '端口', dataIndex: 'port', render: (v: number | null) => v ?? '—' },
          { title: '服务状态', dataIndex: 'service_status', render: (v: string) => svcStatusTag(v) },
          {
            title: 'CPU %', dataIndex: 'cpu_percent',
            render: (v: number) => {
              const color = v > 80 ? '#ff4d4f' : v > 50 ? '#faad14' : '#52c41a';
              return <Text style={{ color }}>{v.toFixed(1)}%</Text>;
            },
          },
          { title: '内存 (MB)', dataIndex: 'mem_mb', render: (v: number) => v.toFixed(1) },
        ]}
      />
    );
  };

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
        <Title level={4} style={{ margin: 0 }}>
          <AppstoreOutlined style={{ marginRight: 8 }} />
          服务组视图
        </Title>
        <Space>
          <Button icon={<ArrowLeftOutlined />} onClick={() => navigate('/topology/servers')}>
            服务器列表
          </Button>
          <Button icon={<ReloadOutlined />} onClick={fetchGroups} loading={loading}>刷新</Button>
        </Space>
      </div>

      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={8}>
          <Card size="small">
            <Statistic title="服务组数" value={groups.length} prefix={<AppstoreOutlined />} />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic title="总实例数" value={totalInstances} prefix={<CloudServerOutlined />} />
          </Card>
        </Col>
        <Col span={8}>
          <Card size="small">
            <Statistic title="分类数" value={new Set(groups.map(g => g.category).filter(Boolean)).size} prefix={<CheckCircleOutlined />} />
          </Card>
        </Col>
      </Row>

      <Input
        placeholder="搜索服务名或分类…"
        prefix={<SearchOutlined />}
        value={search}
        onChange={e => setSearch(e.target.value)}
        style={{ marginBottom: 16, maxWidth: 400 }}
        allowClear
      />

      <Table
        rowKey="id"
        columns={columns as any}
        dataSource={filtered}
        loading={loading}
        expandable={{ expandedRowRender }}
        pagination={{ pageSize: 20, showSizeChanger: true, showTotal: t => `共 ${t} 组` }}
        size="middle"
      />
    </div>
  );
}
