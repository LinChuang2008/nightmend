/**
 * 主机列表页面
 * 展示所有受监控主机的概览信息，支持表格和卡片两种视图模式，
 * 提供按状态筛选和按主机名搜索功能。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Card, Tag, Input, Select, Row, Col, Progress, Typography, Space, Button, Segmented, Empty } from 'antd';
import { CloudServerOutlined, AppstoreOutlined, UnorderedListOutlined, PlusOutlined } from '@ant-design/icons';
import { hostService } from '../services/hosts';
import type { Host } from '../services/hosts';
import PageHeader from '../components/PageHeader';

const { Search } = Input;

/**
 * 主机列表组件
 * 支持分页查询、状态筛选、关键字搜索，以及表格/卡片视图切换
 */
export default function HostList() {
  const [hosts, setHosts] = useState<Host[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  /** 状态筛选值：'online' | 'offline' | '' */
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  /** 视图模式：'table' 表格视图 | 'card' 卡片视图 */
  const [viewMode, setViewMode] = useState<string>('table');
  const navigate = useNavigate();

  /** 获取主机列表数据 (Fetch hosts list data)
   * 根据分页参数、状态筛选、搜索关键词动态构建查询参数
   * 支持按主机名模糊搜索和在线/离线状态过滤
   */
  const fetchHosts = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page, page_size: pageSize };
      if (statusFilter) params.status = statusFilter;
      if (search) params.search = search;
      const { data } = await hostService.list(params);
      setHosts(data.items || []);
      setTotal(data.total || 0);
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  /** 响应分页和筛选参数变化 (React to pagination and filter changes)
   * 监听分页(page/pageSize)和状态筛选变化，自动重新加载数据
   * 搜索功能通过手动触发 fetchHosts，不在依赖数组中
   */
  useEffect(() => { fetchHosts(); }, [page, pageSize, statusFilter, search]);

  /** 表格列配置定义 (Table columns configuration)
   * 包含主机基本信息、资源使用率进度条、标签展示等
   */
  const columns = [
    {
      title: '主机名', dataIndex: 'hostname', key: 'hostname',
      // 主机名渲染为可点击链接，跳转到主机详情页
      render: (text: string, record: Host) => (
        <Button type="link" onClick={() => navigate(`/hosts/${record.id}`)}>{text}</Button>
      ),
    },
    { title: 'IP 地址', dataIndex: 'ip_address', key: 'ip_address' },
    { title: '操作系统', dataIndex: 'os', key: 'os' },
    {
      title: '状态', dataIndex: 'status', key: 'status',
      // 状态显示为彩色标签：在线(绿色) / 离线(红色)
      render: (s: string) => <Tag color={s === 'online' ? 'success' : 'error'}>{s === 'online' ? '在线' : '离线'}</Tag>,
    },
    {
      title: 'CPU', key: 'cpu',
      // CPU 使用率进度条，超过90%显示为异常状态(红色)
      render: (_: unknown, record: Host) => record.latest_metrics ? (
        <Progress percent={Math.round(record.latest_metrics.cpu_percent)} size="small" status={record.latest_metrics.cpu_percent > 90 ? 'exception' : 'normal'} />
      ) : '-',
    },
    {
      title: '内存', key: 'mem',
      // 内存使用率进度条，超过90%显示为异常状态(红色)
      render: (_: unknown, record: Host) => record.latest_metrics ? (
        <Progress percent={Math.round(record.latest_metrics.memory_percent)} size="small" status={record.latest_metrics.memory_percent > 90 ? 'exception' : 'normal'} />
      ) : '-',
    },
    {
      title: '磁盘', key: 'disk',
      // 磁盘使用率进度条，超过90%显示为异常状态(红色)
      render: (_: unknown, record: Host) => record.latest_metrics ? (
        <Progress percent={Math.round(record.latest_metrics.disk_percent)} size="small" status={record.latest_metrics.disk_percent > 90 ? 'exception' : 'normal'} />
      ) : '-',
    },
    {
      title: '标签', dataIndex: 'tags', key: 'tags',
      // 标签处理：支持数组或对象格式，统一转换为标签组件展示
      render: (tags: Record<string, boolean> | string[] | null) => {
        if (!tags) return '-';
        const arr = Array.isArray(tags) ? tags : Object.keys(tags); // 兼容不同数据格式
        return arr.map(t => <Tag key={t}>{t}</Tag>);
      },
    },
  ];

  /** 卡片视图渲染 (Card view rendering)
   * 响应式网格布局，每张卡片包含：主机名、IP、在线状态、CPU/内存使用率
   * 卡片可点击跳转到主机详情页，适合移动端和可视化浏览
   */
  const cardView = (
    <Row gutter={[16, 16]}>
      {hosts.map(host => (
        <Col key={host.id} xs={24} sm={12} md={8} lg={6}>
          <Card
            hoverable
            onClick={() => navigate(`/hosts/${host.id}`)}
            size="small"
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <Space>
                <CloudServerOutlined style={{ fontSize: 20 }} />
                <Typography.Text strong>{host.hostname}</Typography.Text>
                <Tag color={host.status === 'online' ? 'success' : 'error'}>{host.status === 'online' ? '在线' : '离线'}</Tag>
              </Space>
              <Typography.Text type="secondary">{host.ip_address}</Typography.Text>
              {host.latest_metrics && (
                <>
                  <div>CPU: <Progress percent={Math.round(host.latest_metrics.cpu_percent)} size="small" /></div>
                  <div>内存: <Progress percent={Math.round(host.latest_metrics.memory_percent)} size="small" /></div>
                </>
              )}
            </Space>
          </Card>
        </Col>
      ))}
    </Row>
  );

  return (
    <div>
      <PageHeader
        title="服务器列表"
        extra={
          <Space>
            {/* 主机名搜索：立即触发查询并重置分页 */}
            <Search placeholder="搜索主机名" onSearch={v => { setSearch(v); setPage(1); }} style={{ width: 200 }} allowClear />
            {/* 状态筛选：改变时重置到第一页，触发 useEffect 自动查询 */}
            <Select placeholder="状态" allowClear style={{ width: 120 }} onChange={v => { setStatusFilter(v || ''); setPage(1); }}
              options={[{ label: '在线', value: 'online' }, { label: '离线', value: 'offline' }]} />
            <Segmented options={[
              { value: 'table', icon: <UnorderedListOutlined /> },
              { value: 'card', icon: <AppstoreOutlined /> },
            ]} value={viewMode} onChange={v => setViewMode(v as string)} />
          </Space>
        }
      />
      {!loading && hosts.length === 0 && !search && !statusFilter ? (
        <Card>
          <Empty description="暂无服务器，点击添加">
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/settings?tab=tokens')}>添加服务器</Button>
          </Empty>
        </Card>
      ) : viewMode === 'table' ? (
        <Table
          dataSource={hosts}
          columns={columns}
          rowKey="id"
          loading={loading}
          pagination={{ current: page, pageSize, total, onChange: (p, ps) => { setPage(p); setPageSize(ps); } }}
        />
      ) : cardView}
    </div>
  );
}
