/**
 * 主机列表页面
 * 展示所有受监控主机的概览信息，支持表格和卡片两种视图模式，
 * 提供按状态筛选和按主机名搜索功能。
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Table, Card, Tag, Input, Select, Row, Col, Progress, Typography, Space, Button, Segmented, Empty, Tooltip, Modal, message } from 'antd';
import { CloudServerOutlined, AppstoreOutlined, UnorderedListOutlined, PlusOutlined, EditOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { hostService } from '../services/hosts';
import type { Host } from '../services/hosts';
import PageHeader from '../components/PageHeader';

const { Search } = Input;

/**
 * 获取主机显示名称（优先使用 display_name）
 */
const getDisplayName = (host: Host): string => {
  return host.display_name || host.hostname;
};

/**
 * 获取主机显示 IP（优先内网 IP，否则公网 IP，最后兼容旧字段）
 */
const getDisplayIp = (host: Host): string => {
  return host.private_ip || host.ip_address || host.public_ip || 'N/A';
};

/**
 * 判断是否有多个 IP 需要显示提示
 */
const hasMultipleIps = (host: Host): boolean => {
  return !!(host.private_ip && host.public_ip);
};

/**
 * 主机列表组件
 * 支持分页查询、状态筛选、关键字搜索，以及表格/卡片视图切换
 */
export default function HostList() {
  const { t } = useTranslation();
  const [hosts, setHosts] = useState<Host[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [search, setSearch] = useState('');
  const [viewMode, setViewMode] = useState<string>('table');
  const navigate = useNavigate();

  // 编辑相关状态
  const [editingHost, setEditingHost] = useState<Host | null>(null);
  const [editModalVisible, setEditModalVisible] = useState(false);
  const [displayNameInput, setDisplayNameInput] = useState('');
  const [updating, setUpdating] = useState(false);

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

  useEffect(() => { fetchHosts(); }, [page, pageSize, statusFilter, search]);

  // 打开编辑模态框
  const openEditModal = (host: Host) => {
    setEditingHost(host);
    setDisplayNameInput(host.display_name || '');
    setEditModalVisible(true);
  };

  // 保存显示名称
  const saveDisplayName = async () => {
    if (!editingHost) return;

    // 验证不能为纯空格
    if (displayNameInput.trim() === '') {
      message.error(t('hosts.displayNameCannotBeEmpty'));
      return;
    }

    setUpdating(true);
    try {
      const updateData = displayNameInput.trim() ? { display_name: displayNameInput.trim() } : { display_name: null };
      await hostService.update(editingHost.id.toString(), updateData);

      // 更新本地状态
      setHosts(hosts.map(h =>
        h.id === editingHost.id ? { ...h, display_name: updateData.display_name } : h
      ));

      message.success(t('hosts.displayNameUpdated'));
      setEditModalVisible(false);
    } catch {
      message.error(t('hosts.updateFailed'));
    } finally {
      setUpdating(false);
    }
  };

  const columns = [
    {
      title: t('hosts.hostname'), dataIndex: 'hostname', key: 'hostname',
      render: (_: string, record: Host) => {
        const displayName = getDisplayName(record);
        const hasCustomName = record.display_name && record.display_name !== record.hostname;
        return (
          <Space size={4}>
            <Button type="link" onClick={() => navigate(`/hosts/${record.id}`)} style={{ padding: 0 }}>
              {displayName}
            </Button>
            <Button
              type="text"
              icon={<EditOutlined />}
              size="small"
              onClick={(e) => { e.stopPropagation(); openEditModal(record); }}
              style={{ padding: 0, fontSize: 12 }}
            />
            {hasCustomName && (
              <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                ({record.hostname})
              </Typography.Text>
            )}
          </Space>
        );
      },
    },
    {
      title: t('hosts.ip'), dataIndex: 'ip_address', key: 'ip',
      render: (_: string, record: Host) => {
        const displayIp = getDisplayIp(record);
        if (hasMultipleIps(record)) {
          return (
            <Tooltip title={
              <div>
                <div>{t('hosts.publicIp')}:{record.public_ip}</div>
                <div>{t('hosts.privateIp')}: {record.private_ip}</div>
              </div>
            }>
              <Typography.Text>{displayIp} <Typography.Text type="secondary">(+1)</Typography.Text></Typography.Text>
            </Tooltip>
          );
        }
        return displayIp;
      },
    },
    { title: t('hosts.os'), dataIndex: 'os', key: 'os' },
    {
      title: t('hosts.status'), dataIndex: 'status', key: 'status',
      render: (s: string) => {
        const tone =
          s === 'online'    ? { color: 'var(--nm-accent)',     bg: 'rgba(16,185,129,0.10)',  border: 'rgba(16,185,129,0.28)', glow: true,  text: t('hosts.online') }
          : s === 'offline' ? { color: 'var(--nm-error)',      bg: 'rgba(239,68,68,0.12)',   border: 'rgba(239,68,68,0.28)',  glow: false, text: t('hosts.offline') }
          :                   { color: 'var(--nm-text-dim)',   bg: 'rgba(113,113,122,0.10)', border: 'var(--nm-border)',      glow: false, text: t('common.unknown') };
        return (
          <span style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 5,
            fontFamily: 'var(--nm-font-mono)',
            fontSize: 10.5,
            padding: '2px 8px',
            borderRadius: 3,
            border: `1px solid ${tone.border}`,
            background: tone.bg,
            color: tone.color,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            fontWeight: 600,
            whiteSpace: 'nowrap',
          }}>
            {tone.glow && <span style={{ width: 6, height: 6, borderRadius: '50%', background: tone.color, boxShadow: `0 0 6px ${tone.color}` }} />}
            {tone.text}
          </span>
        );
      },
    },
    {
      title: t('hosts.cpu'), key: 'cpu',
      render: (_: unknown, record: Host) => record.latest_metrics ? (
        <Progress percent={Math.round(record.latest_metrics.cpu_percent)} size="small" status={record.latest_metrics.cpu_percent > 90 ? 'exception' : 'normal'} />
      ) : '-',
    },
    {
      title: t('hosts.memory'), key: 'mem',
      render: (_: unknown, record: Host) => record.latest_metrics ? (
        <Progress percent={Math.round(record.latest_metrics.memory_percent)} size="small" status={record.latest_metrics.memory_percent > 90 ? 'exception' : 'normal'} />
      ) : '-',
    },
    {
      title: t('hosts.disk'), key: 'disk',
      render: (_: unknown, record: Host) => record.latest_metrics ? (
        <Progress percent={Math.round(record.latest_metrics.disk_percent)} size="small" status={record.latest_metrics.disk_percent > 90 ? 'exception' : 'normal'} />
      ) : '-',
    },
    {
      title: t('hosts.tags'), dataIndex: 'tags', key: 'tags',
      render: (tags: Record<string, boolean> | string[] | null) => {
        if (!tags) return '-';
        const arr = Array.isArray(tags) ? tags : Object.keys(tags);
        return arr.map(tag => <Tag key={tag}>{tag}</Tag>);
      },
    },
  ];

  const cardView = (
    <Row gutter={[16, 16]}>
      {hosts.map(host => {
        const displayName = getDisplayName(host);
        const displayIp = getDisplayIp(host);
        const hasCustomName = host.display_name && host.display_name !== host.hostname;
        return (
          <Col key={host.id} xs={24} sm={12} md={8} lg={6}>
            <Card
              hoverable
              onClick={() => navigate(`/hosts/${host.id}`)}
              size="small"
            >
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                  <CloudServerOutlined style={{ fontSize: 20 }} />
                  <Space direction="vertical" size={0}>
                    <Typography.Text strong>{displayName}</Typography.Text>
                    {hasCustomName && (
                      <Typography.Text type="secondary" style={{ fontSize: 12 }}>
                        {host.hostname}
                      </Typography.Text>
                    )}
                  </Space>
                  <Tag color={host.status === 'online' ? 'success' : host.status === 'offline' ? 'error' : 'default'}>
                    {host.status === 'online' ? t('hosts.online') : host.status === 'offline' ? t('hosts.offline') : t('common.unknown')}
                  </Tag>
                </Space>
                {hasMultipleIps(host) ? (
                  <Tooltip title={
                    <div>
                      <div>{t('hosts.publicIp')}:{host.public_ip}</div>
                      <div>内网: {host.private_ip}</div>
                    </div>
                  }>
                    <Typography.Text type="secondary">{displayIp} <Typography.Text type="secondary">(+1)</Typography.Text></Typography.Text>
                  </Tooltip>
                ) : (
                  <Typography.Text type="secondary">{displayIp}</Typography.Text>
                )}
                {host.latest_metrics && (
                  <>
                    <div>CPU: <Progress percent={Math.round(host.latest_metrics.cpu_percent)} size="small" /></div>
                    <div>{t('hosts.memory')}: <Progress percent={Math.round(host.latest_metrics.memory_percent)} size="small" /></div>
                  </>
                )}
              </Space>
            </Card>
          </Col>
        );
      })}
    </Row>
  );

  return (
    <div>
      <PageHeader
        title={t('hosts.title')}
        extra={
          <Space>
            <Search placeholder={t('hosts.searchPlaceholder')} onSearch={v => { setSearch(v); setPage(1); }} style={{ width: 200 }} allowClear />
            <Select placeholder={t('hosts.status')} allowClear style={{ width: 120 }} onChange={v => { setStatusFilter(v || ''); setPage(1); }}
              options={[{ label: t('hosts.online'), value: 'online' }, { label: t('hosts.offline'), value: 'offline' }]} />
            <Segmented options={[
              { value: 'table', icon: <UnorderedListOutlined /> },
              { value: 'card', icon: <AppstoreOutlined /> },
            ]} value={viewMode} onChange={v => setViewMode(v as string)} />
          </Space>
        }
      />
      {!loading && hosts.length === 0 && !search && !statusFilter ? (
        <Card>
          <Empty description={t('hosts.noServers')}>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/settings?tab=tokens')}>{t('hosts.addServer')}</Button>
          </Empty>
        </Card>
      ) : viewMode === 'table' ? (
        <Table
          dataSource={hosts}
          columns={columns}
          rowKey="id"
          loading={loading}
          scroll={{ x: 900 }}
          pagination={{ current: page, pageSize, total, onChange: (p, ps) => { setPage(p); setPageSize(ps); } }}
        />
      ) : cardView}

      {/* 编辑显示名称模态框 */}
      <Modal
        title={t('hosts.editDisplayName')}
        open={editModalVisible}
        onOk={saveDisplayName}
        onCancel={() => setEditModalVisible(false)}
        confirmLoading={updating}
        okText={t('common.save')}
        cancelText={t('common.cancel')}
      >
        <Space direction="vertical" style={{ width: '100%' }}>
          <Typography.Text>{t('hosts.hostname')}: {editingHost?.hostname}</Typography.Text>
          <Input
            placeholder={t('hosts.enterDisplayName')}
            value={displayNameInput}
            onChange={(e) => setDisplayNameInput(e.target.value)}
            onPressEnter={saveDisplayName}
            maxLength={100}
            showCount
          />
        </Space>
      </Modal>
    </div>
  );
}
