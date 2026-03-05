/**
 * 服务监控列表页面
 *
 * 按服务器分组展示服务，每个服务器一个折叠卡片，内含该服务器上的所有服务。
 * 支持按分类（中间件/业务系统）和状态筛选。
 * 单台服务器时平铺显示，多台时分组显示。
 */
import { useEffect, useState, useMemo } from 'react';
// useMemo still used for hostCount
import { useNavigate } from 'react-router-dom';
import {
  Table, Card, Tag, Typography, Progress, Button,
  Row, Col, Select, Space, Statistic, Collapse, Badge, Empty,
} from 'antd';
import {
  CloudServerOutlined, DatabaseOutlined, AppstoreOutlined,
  ApiOutlined, DesktopOutlined, ReloadOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { serviceService } from '../services/services';
import type { Service } from '../services/services';
import api from '../services/api';
import PageHeader from '../components/PageHeader';

const { Text } = Typography;

/* ==================== 类型定义 ==================== */

/** 主机分组数据 */
interface HostGroup {
  host_id: number;
  hostname: string;
  ip: string;
  host_status: string;
  services: ServiceItem[];
}

/** 带主机信息的服务 */
interface ServiceItem extends Service {
  host_info?: { id: number; hostname: string; ip: string; status: string } | null;
}

/* ==================== 分类配置 ==================== */

const CATEGORY_CONFIG: Record<string, { color: string; icon: React.ReactNode }> = {
  middleware:      { color: 'purple', icon: <DatabaseOutlined /> },
  business:       { color: 'blue',   icon: <AppstoreOutlined /> },
  infrastructure: { color: 'cyan',   icon: <CloudServerOutlined /> },
};

/** 分类标签组件 (Category tag component)
 * 根据服务分类显示带图标的彩色标签
 * 支持中间件、业务系统、基础设施三种预定义分类，未知分类显示为默认样式
 */
const CategoryTag = ({ category }: { category?: string }) => {
  const { t } = useTranslation();
  const config = CATEGORY_CONFIG[category || ''];
  const labelMap: Record<string, string> = {
    middleware: t('services.middleware'),
    business: t('services.business'),
    infrastructure: t('services.infrastructure'),
  };
  const label = category ? (labelMap[category] || category) : t('services.uncategorized');
  return (
    <Tag
      color={config?.color || 'default'}
      icon={config?.icon || <ApiOutlined />}
      style={{ marginRight: 0 }}
    >
      {label}
    </Tag>
  );
};

/** 状态颜色映射 (Status color mapping)
 * 将服务状态转换为 Ant Design 标签颜色：健康=绿色，降级=橙色，其他=红色
 */
const statusColor = (s: string) => {
  if (s === 'healthy' || s === 'up') return 'success';
  if (s === 'degraded') return 'warning';
  return 'error';
};


/* ==================== 组件 ==================== */

export default function ServiceList() {
  const { t } = useTranslation();
  const [, setServices] = useState<ServiceItem[]>([]);
  const [hostGroups, setHostGroups] = useState<HostGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [slaMap, setSlaMap] = useState<Record<string, string>>({});
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [categoryFilter, setCategoryFilter] = useState<string | undefined>(undefined);
  /** 全局统计（不受筛选影响） */
  const [globalStats, setGlobalStats] = useState({ total: 0, middleware: 0, business: 0, infrastructure: 0, healthy: 0, unhealthy: 0 });
  const navigate = useNavigate();

  /** 获取按主机分组的服务数据 (Fetch services grouped by host)
   * 使用 group_by_host=true 参数获取主机分组数据结构
   * 支持按状态和分类筛选，同时获取不受筛选影响的全局统计信息
   */
  const fetchData = async () => {
    setLoading(true);
    try {
      const params: Record<string, unknown> = { page: 1, page_size: 100, group_by_host: true };
      if (statusFilter) params.status = statusFilter;
      if (categoryFilter) params.category = categoryFilter;
      const [{ data }, slaRes] = await Promise.all([
        serviceService.list(params),
        api.get('/sla/status').catch(() => ({ data: [] })),
      ]);
      setServices(data.items || []);
      setHostGroups(data.host_groups || []);
      if (data.stats) setGlobalStats(data.stats);
      // 构建 slaMap: service_id -> sla_status
      const map: Record<string, string> = {};
      const slaList = Array.isArray(slaRes.data) ? slaRes.data : (slaRes.data?.items || []);
      for (const item of slaList) {
        if (item.service_id != null) map[String(item.service_id)] = item.status || item.sla_status || 'no_data';
      }
      setSlaMap(map);
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  /** 响应筛选条件变化 (React to filter changes)
   * 监听状态和分类筛选器变化，自动重新获取匹配的服务数据
   * 保持界面与筛选条件同步
   */
  useEffect(() => { fetchData(); }, [statusFilter, categoryFilter]); // eslint-disable-line

  /** 主机数量从全局统计独立（hostGroups 可能因筛选变少） */
  const hostCount = useMemo(() => hostGroups.length, [hostGroups]);

  /** 服务表格列配置 (Service table columns configuration)
   * 包含服务名、分类、目标地址、类型、状态、可用率、最后检查时间等信息
   */
  const columns = [
    {
      title: t('services.serviceName'),
      dataIndex: 'name',
      key: 'name',
      // 服务名渲染为可点击链接，跳转到服务详情页
      render: (text: string, record: ServiceItem) => (
        <Button type="link" style={{ padding: 0 }} onClick={() => navigate(`/services/${record.id}`)}>
          {text}
        </Button>
      ),
    },
    {
      title: t('services.category'),
      dataIndex: 'category',
      key: 'category',
      width: 110,
      // 使用自定义分类标签组件，带图标和颜色区分
      render: (cat: string) => <CategoryTag category={cat} />,
    },
    {
      title: t('services.target'),
      key: 'url',
      ellipsis: true,
      // 显示服务的目标地址或URL，兼容不同字段名
      render: (_: unknown, r: ServiceItem) => (
        <Text type="secondary" style={{ fontSize: 13 }}>{r.target || r.url || '-'}</Text>
      ),
    },
    {
      title: t('services.checkType'),
      key: 'check_type',
      width: 80,
      // 显示检查类型（HTTP、TCP等），转换为大写
      render: (_: unknown, r: ServiceItem) => (
        <Tag>{(r.type || r.check_type || '')?.toUpperCase()}</Tag>
      ),
    },
    {
      title: t('common.status'),
      dataIndex: 'status',
      key: 'status',
      width: 80,
      // 状态标签：健康=绿色，异常=红色，降级=橙色
      render: (s: string) => {
        const text = (s === 'healthy' || s === 'up') ? t('services.healthy')
          : (s === 'degraded') ? t('services.degraded')
          : t('common.unhealthy');
        return <Tag color={statusColor(s)}>{text}</Tag>;
      },
    },
    {
      title: t('services.uptime24h'),
      dataIndex: 'uptime_percent',
      key: 'uptime',
      width: 150,
      // 可用率进度条：99%以上=绿色，95%以上=正常，以下=异常红色
      render: (v: number) => (
        <Progress
          percent={v != null ? Math.round(v * 100) / 100 : 0}
          size="small"
          status={v >= 99 ? 'success' : v >= 95 ? 'normal' : 'exception'}
        />
      ),
    },
    {
      title: t('services.lastCheck'),
      dataIndex: 'last_check',
      key: 'last_check',
      width: 170,
      // 最后检查时间本地化显示
      render: (v: string) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: 'SLA',
      key: 'sla',
      width: 90,
      render: (_: unknown, r: ServiceItem) => {
        const status = slaMap[String(r.id)];
        if (status === undefined) return <Tag color="default">{t('services.slaNotConfigured')}</Tag>;
        if (status === 'compliant' || status === 'met') return <Tag color="green">{t('services.slaMet')}</Tag>;
        if (status === 'non_compliant' || status === 'violated' || status === 'breached') return <Tag color="red">{t('services.slaNotMet')}</Tag>;
        if (status === 'no_data') return <Tag>-</Tag>;
        return <Tag color="default">{t('services.slaNotConfigured')}</Tag>;
      },
    },
  ];

  /** 渲染服务表格 (Render services table)
   * 为每个主机分组渲染服务列表表格，紧凑模式无分页
   * @param items 该主机下的服务列表
   */
  const renderServiceTable = (items: ServiceItem[]) => (
    <Table
      dataSource={items}
      columns={columns}
      rowKey="id"
      size="small"
      pagination={false}
    />
  );

  /** 渲染主机分组头部 (Render host group header)
   * 显示主机名、IP、在线状态，以及服务健康统计和分类计数
   * 包含健康服务数/总服务数的徽章和分类标签
   */
  const renderHostHeader = (group: HostGroup) => {
    // 计算该主机的服务健康统计
    const healthyCount = group.services.filter(s => s.status === 'up' || s.status === 'healthy').length;
    const totalCount = group.services.length;
    // 按分类计数：中间件和业务系统
    const mwCount = group.services.filter(s => s.category === 'middleware').length;
    const bizCount = group.services.filter(s => s.category === 'business').length;
    const isOnline = group.host_status === 'online';

    return (
      <Space size={16} style={{ width: '100%' }}>
        <Space>
          {/* 主机图标：在线绿色，离线红色 */}
          <DesktopOutlined style={{ fontSize: 18, color: isOnline ? '#52c41a' : '#ff4d4f' }} />
          <span style={{ fontWeight: 600, fontSize: 15 }}>{group.hostname}</span>
          {group.ip && <Text type="secondary">({group.ip})</Text>}
          <Tag color={isOnline ? 'success' : 'error'}>{isOnline ? t('common.online') : t('common.offline')}</Tag>
        </Space>
        <Space size={12}>
          {/* 健康服务数徽章：全部健康=绿色，否则=橙色 */}
          <Badge
            count={`${healthyCount}/${totalCount}`}
            style={{ backgroundColor: healthyCount === totalCount ? '#52c41a' : '#faad14' }}
          />
          {/* 分类标签：只显示存在的分类 */}
          {mwCount > 0 && <Tag color="purple">{t('services.middleware')} {mwCount}</Tag>}
          {bizCount > 0 && <Tag color="blue">{t('services.business')} {bizCount}</Tag>}
        </Space>
      </Space>
    );
  };

  return (
    <div>
      {/* 标题 + 统计 */}
      <PageHeader
        title={t('services.title')}
        tags={<Tag icon={<DesktopOutlined />} color="default">{hostCount} {t('services.servers')}</Tag>}
        extra={
          <Space size={20}>
            <Statistic title={t('services.totalServices')} value={globalStats.total} valueStyle={{ fontSize: 18 }} />
            <Statistic
              title={t('services.middleware')}
              value={globalStats.middleware}
              prefix={<DatabaseOutlined />}
              valueStyle={{ fontSize: 18, color: '#722ed1' }}
            />
            <Statistic
              title={t('services.business')}
              value={globalStats.business}
              prefix={<AppstoreOutlined />}
              valueStyle={{ fontSize: 18, color: '#1890ff' }}
            />
            <Statistic
              title={t('common.healthy')}
              value={globalStats.healthy}
              valueStyle={{ fontSize: 18, color: '#52c41a' }}
            />
            <Statistic
              title={t('common.unhealthy')}
              value={globalStats.unhealthy}
              valueStyle={{ fontSize: 18, color: globalStats.unhealthy > 0 ? '#ff4d4f' : '#d9d9d9' }}
            />
          </Space>
        }
      />

      {/* 筛选器 */}
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <Space>
            <Select
              placeholder={t('services.serviceCategoryFilter')}
              allowClear
              style={{ width: 130 }}
              value={categoryFilter}
              onChange={(v) => setCategoryFilter(v || undefined)}
              options={[
                { label: `🗄️ ${t('services.middleware')}`, value: 'middleware' },
                { label: `📦 ${t('services.business')}`, value: 'business' },
                { label: `☁️ ${t('services.infrastructure')}`, value: 'infrastructure' },
              ]}
            />
            <Select
              placeholder={t('services.runningStatusFilter')}
              allowClear
              style={{ width: 120 }}
              value={statusFilter}
              onChange={(v) => setStatusFilter(v || undefined)}
              options={[
                { label: `✅ ${t('services.healthy')}`, value: 'up' },
                { label: `❌ ${t('common.unhealthy')}`, value: 'down' },
              ]}
            />
          </Space>
        </Col>
        <Col>
          <Button icon={<ReloadOutlined />} onClick={fetchData} loading={loading}>
            {t('common.refresh')}
          </Button>
        </Col>
      </Row>

      {/* 服务列表：统一折叠面板，点击展开 */}
      {loading ? (
        <Card loading />
      ) : hostGroups.length === 0 ? (
        <Card><Empty description={t('services.noServices')} /></Card>
      ) : (
        <Collapse
          defaultActiveKey={[]}
          items={hostGroups.map(group => ({
            key: String(group.host_id),
            label: renderHostHeader(group),
            children: renderServiceTable(group.services),
            style: { marginBottom: 12, borderRadius: 8, overflow: 'hidden' },
          }))}
          style={{ background: 'transparent' }}
        />
      )}
    </div>
  );
}
