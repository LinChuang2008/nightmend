/**
 * 系统设置页面
 *
 * 包含两个 Tab：
 * 1. 常规设置 - 动态加载后端配置项，以表单形式展示和保存
 * 2. Agent Token 管理 - 管理用于 Agent 接入的 API Token，支持创建和吊销
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card, Form, InputNumber, Button, Typography, Spin, message, notification, Tabs, Table, Tag, Space, Modal, Input, Tooltip } from 'antd';
import { PlusOutlined, ExclamationCircleOutlined, CopyOutlined, CheckOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import api from '../services/api';
import PageHeader from '../components/PageHeader';

/** Agent Token 数据结构 */
interface AgentToken {
  id: string;
  /** Token 名称（用户自定义标识） */
  name: string;
  /** Token 值 */
  token: string;
  /** 是否处于活跃状态 */
  is_active: boolean;
  created_at: string;
}

/**
 * 系统设置页面组件
 */
export default function Settings() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  /** 系统配置项：key → { value, description } */
  const [settings, setSettings] = useState<Record<string, { value: string; description: string }>>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // ========== Agent Token 管理 ==========
  const [tokens, setTokens] = useState<AgentToken[]>([]);
  const [tokensLoading, setTokensLoading] = useState(false);
  const [tokenModalOpen, setTokenModalOpen] = useState(false);
  const [newTokenName, setNewTokenName] = useState('');

  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();
  /** 已复制的 token id，用于显示对勾图标 */
  const [copiedId, setCopiedId] = useState<string | null>(null);

  /** 复制文本到剪贴板，兼容不支持 navigator.clipboard 的环境 */
  const copyToClipboard = (text: string, id: string) => {
    const succeed = () => {
      setCopiedId(id);
      messageApi.success(t('common.copied'));
      setTimeout(() => setCopiedId(null), 2000);
    };
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(succeed).catch(() => execCommandCopy(text, id, succeed));
    } else {
      execCommandCopy(text, id, succeed);
    }
  };

  const execCommandCopy = (text: string, _id: string, succeed: () => void) => {
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.cssText = 'position:fixed;top:-9999px;left:-9999px';
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    try {
      document.execCommand('copy');
      succeed();
    } catch {
      messageApi.error('复制失败，请手动复制');
    } finally {
      document.body.removeChild(textarea);
    }
  };

  /** 获取系统配置项并填充表单 */
  const fetchSettings = async () => {
    setLoading(true);
    try {
      const { data } = await api.get('/settings');
      setSettings(data);
      // 将字符串值转为数字填入表单
      const formValues: Record<string, number> = {};
      for (const [key, val] of Object.entries(data)) {
        formValues[key] = parseInt((val as { value: string }).value, 10);
      }
      form.setFieldsValue(formValues);
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  /** 获取 Agent Token 列表 */
  const fetchTokens = async () => {
    setTokensLoading(true);
    try {
      const { data } = await api.get('/agent-tokens');
      setTokens(Array.isArray(data) ? data : data.items || []);
    } catch { /* ignore */ } finally { setTokensLoading(false); }
  };

  useEffect(() => { fetchSettings(); }, []);

  /** 保存系统配置 */
  const handleSave = async (values: Record<string, number>) => {
    setSaving(true);
    try {
      await api.put('/settings', values);
      messageApi.success('设置已保存');
    } catch { messageApi.error('保存失败'); } finally { setSaving(false); }
  };

  /** 创建新的 Agent Token */
  const handleCreateToken = async () => {
    if (!newTokenName.trim()) return;
    try {
      const { data } = await api.post('/agent-tokens', { name: newTokenName });
      messageApi.success('Token 已创建');
      setTokenModalOpen(false);
      setNewTokenName('');
      fetchTokens();
      const tokenId = data?.id || newTokenName;
      notification.info({
        key: `guide-alert-${tokenId}`,
        message: '主机添加成功',
        description: '建议为该主机配置告警规则，及时发现异常',
        btn: <Button size='small' type='primary' onClick={() => navigate('/alerts?tab=rules')}>立即配置</Button>,
        duration: 8,
      });
    } catch { messageApi.error('创建失败'); }
  };

  /** 吊销 Agent Token（带确认弹窗） */
  const handleRevokeToken = (id: string) => {
    Modal.confirm({
      title: '确认吊销此 Token？',
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        try {
          await api.delete(`/agent-tokens/${id}`);
          messageApi.success('已吊销');
          fetchTokens();
        } catch { messageApi.error('操作失败'); }
      },
    });
  };

  /** Token 列表表格列定义 */
  const tokenColumns = [
    { title: '名称', dataIndex: 'name' },
    {
      title: 'Token', dataIndex: 'token',
      render: (t: string, record: AgentToken) => (
        <Space>
          <Typography.Text code>{t?.substring(0, 16)}...</Typography.Text>
          <Tooltip title={copiedId === record.id ? '已复制' : '复制完整 Token'}>
            <Button
              type="text"
              size="small"
              icon={copiedId === record.id ? <CheckOutlined style={{ color: '#52c41a' }} /> : <CopyOutlined />}
              onClick={() => copyToClipboard(t, record.id)}
            />
          </Tooltip>
        </Space>
      ),
    },
    { title: '状态', dataIndex: 'is_active', render: (v: boolean) => <Tag color={v ? 'success' : 'default'}>{v ? '活跃' : '已吊销'}</Tag> },
    { title: '创建时间', dataIndex: 'created_at', render: (t: string) => new Date(t).toLocaleString() },
    {
      title: '操作', key: 'action',
      render: (_: unknown, record: AgentToken) => record.is_active ? (
        <Button type="link" size="small" danger onClick={() => handleRevokeToken(record.id)}>吊销</Button>
      ) : '-',
    },
  ];

  if (loading) return <Spin size="large" style={{ display: 'block', margin: '100px auto' }} />;

  return (
    <div>
      {contextHolder}
      <PageHeader title="系统设置" />
      <Tabs defaultActiveKey="general" onChange={k => { if (k === 'tokens') fetchTokens(); }} items={[
        {
          key: 'general', label: '常规设置',
          children: (
            <Card>
              {/* 动态生成配置项表单，description 作为 label 展示 */}
              <Form form={form} layout="vertical" onFinish={handleSave} style={{ maxWidth: 500 }}>
                {Object.entries(settings).map(([key, meta]) => (
                  <Form.Item key={key} name={key} label={meta.description || key} rules={[{ required: true }]}>
                    <InputNumber style={{ width: '100%' }} />
                  </Form.Item>
                ))}
                <Form.Item>
                  <Button type="primary" htmlType="submit" loading={saving}>保存设置</Button>
                </Form.Item>
              </Form>
            </Card>
          ),
        },
        {
          key: 'tokens', label: 'Agent Token 管理',
          children: (
            <>
              <Space style={{ marginBottom: 16 }}>
                <Button type="primary" icon={<PlusOutlined />} onClick={() => setTokenModalOpen(true)}>创建 Token</Button>
              </Space>
              <Card>
                <Table dataSource={tokens} columns={tokenColumns} rowKey="id" loading={tokensLoading} pagination={false} />
              </Card>
              {/* 创建 Token 弹窗 */}
              <Modal title="创建 Agent Token" open={tokenModalOpen} onCancel={() => setTokenModalOpen(false)} onOk={handleCreateToken}>
                <Input placeholder="Token 名称" value={newTokenName} onChange={e => setNewTokenName(e.target.value)} />
              </Modal>
            </>
          ),
        },
      ]} />
    </div>
  );
}
