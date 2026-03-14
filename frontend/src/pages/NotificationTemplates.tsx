/**
 * 通知模板管理页面
 * 提供通知模板的增删改查功能，支持变量预览。
 */
import { useEffect, useState } from 'react';
import { Table, Card, Typography, Button, Modal, Form, Input, Switch, Select, Tag, Space, message } from 'antd';
import { ExclamationCircleOutlined, EyeOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { notificationTemplateService } from '../services/notificationTemplates';
import type { NotificationTemplate } from '../services/notificationTemplates';

const { TextArea } = Input;

/** 渠道类型 value 列表 */
const CHANNEL_TYPES = ['all', 'webhook', 'email', 'dingtalk', 'feishu', 'wecom', 'slack', 'telegram'] as const;

/** 渠道类型 Tag 颜色映射 */
const TYPE_TAG_COLOR: Record<string, string | undefined> = {
  all: 'orange',
  webhook: undefined,
  email: 'blue',
  dingtalk: 'cyan',
  feishu: 'purple',
  wecom: 'green',
  slack: 'geekblue',
  telegram: 'magenta',
};

/** 渠道类型 i18n key 映射 */
const TYPE_LABEL_KEY: Record<string, string> = {
  all: 'notifications.typeAll',
  webhook: 'notifications.typeWebhook',
  email: 'notifications.typeEmail',
  dingtalk: 'notifications.typeDingtalk',
  feishu: 'notifications.typeFeishu',
  wecom: 'notifications.typeWecom',
  slack: 'notifications.typeSlack',
  telegram: 'notifications.typeTelegram',
};

/** 可用模板变量 */
const AVAILABLE_VARS = ['{title}', '{severity}', '{message}', '{metric_value}', '{threshold}', '{host_id}', '{fired_at}', '{resolved_at}'];

/** 预览用示例数据 */
const SAMPLE_DATA: Record<string, string> = {
  '{title}': 'CPU 使用率过高',
  '{severity}': 'critical',
  '{message}': '主机 web-01 CPU 使用率达到 95%',
  '{metric_value}': '95.2',
  '{threshold}': '90',
  '{host_id}': 'web-01',
  '{fired_at}': '2026-02-17 11:30:00',
  '{resolved_at}': '2026-02-17 11:45:00',
};

/** 用示例数据替换模板中的变量 */
function renderPreview(template: string): string {
  let result = template;
  for (const [k, v] of Object.entries(SAMPLE_DATA)) {
    result = result.replaceAll(k, v);
  }
  return result;
}

/**
 * 通知模板管理组件
 */
export default function NotificationTemplates() {
  const { t } = useTranslation();
  const [templates, setTemplates] = useState<NotificationTemplate[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationTemplate | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewContent, setPreviewContent] = useState<{ subject?: string; body: string }>({ body: '' });
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();

  /** 获取模板列表 */
  const fetchList = async () => {
    setLoading(true);
    try {
      const { data } = await notificationTemplateService.fetchTemplates();
      setTemplates(Array.isArray(data) ? data : []);
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  useEffect(() => { fetchList(); }, []);

  /** 打开新建弹窗 */
  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ channel_type: 'all', is_default: false });
    setModalOpen(true);
  };

  /** 打开编辑弹窗 */
  const openEdit = (record: NotificationTemplate) => {
    setEditing(record);
    form.resetFields();
    form.setFieldsValue({
      name: record.name,
      channel_type: record.channel_type,
      subject_template: record.subject_template,
      body_template: record.body_template,
      is_default: record.is_default,
    });
    setModalOpen(true);
  };

  /** 提交创建/编辑 */
  const handleSubmit = async (values: Record<string, unknown>) => {
    const payload = {
      name: values.name as string,
      channel_type: values.channel_type as string,
      subject_template: values.subject_template as string | null || null,
      body_template: values.body_template as string,
      is_default: values.is_default as boolean,
    };
    try {
      if (editing) {
        await notificationTemplateService.updateTemplate(editing.id, payload);
        messageApi.success(t('notifications.updatedSuccess'));
      } else {
        await notificationTemplateService.createTemplate(payload);
        messageApi.success(t('notifications.createSuccess'));
      }
      setModalOpen(false);
      fetchList();
    } catch { messageApi.error(editing ? t('notifications.updateFailed') : t('notifications.createFailed')); }
  };

  /** 删除模板 */
  const handleDelete = (id: number) => {
    Modal.confirm({
      title: t('notifications.confirmDeleteTemplate'),
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        try {
          await notificationTemplateService.deleteTemplate(id);
          messageApi.success(t('notifications.deletedSuccess'));
          fetchList();
        } catch { messageApi.error(t('notifications.deleteFailed')); }
      },
    });
  };

  /** 预览模板 */
  const handlePreview = (record: NotificationTemplate) => {
    setPreviewContent({
      subject: record.subject_template ? renderPreview(record.subject_template) : undefined,
      body: renderPreview(record.body_template),
    });
    setPreviewOpen(true);
  };

  /** 切换默认状态 */
  const handleToggleDefault = async (record: NotificationTemplate) => {
    try {
      await notificationTemplateService.updateTemplate(record.id, { is_default: !record.is_default });
      messageApi.success(t('notifications.updatedSuccess'));
      fetchList();
    } catch { messageApi.error(t('notifications.actionFailed')); }
  };

  /** 表格列定义 */
  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: t('common.name'), dataIndex: 'name' },
    {
      title: t('notifications.channelType'), dataIndex: 'channel_type', width: 120,
      render: (v: string) => <Tag color={TYPE_TAG_COLOR[v]}>{TYPE_LABEL_KEY[v] ? t(TYPE_LABEL_KEY[v]) : v}</Tag>,
    },
    {
      title: t('notifications.default'), dataIndex: 'is_default', width: 80,
      render: (v: boolean, r: NotificationTemplate) => (
        <Switch checked={v} onChange={() => handleToggleDefault(r)} size="small" />
      ),
    },
    { title: t('common.createdAt'), dataIndex: 'created_at', render: (v: string) => new Date(v).toLocaleString() },
    {
      title: t('common.actions'), key: 'action', width: 200,
      render: (_: unknown, r: NotificationTemplate) => (
        <Space>
          <Button type="link" size="small" icon={<EyeOutlined />} onClick={() => handlePreview(r)}>{t('common.preview')}</Button>
          <Button type="link" size="small" onClick={() => openEdit(r)}>{t('common.edit')}</Button>
          <Button type="link" danger size="small" onClick={() => handleDelete(r.id)}>{t('common.delete')}</Button>
        </Space>
      ),
    },
  ];

  return (
    <div>
      {contextHolder}
      <Typography.Title level={4}>{t('notifications.templates')}</Typography.Title>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={openCreate}>{t('notifications.addTemplate')}</Button>
      </Space>
      <Card>
        <Table dataSource={templates} columns={columns} rowKey="id" loading={loading} pagination={false} />
      </Card>

      {/* 新建/编辑模板弹窗 */}
      <Modal
        title={editing ? t('notifications.editTemplate') : t('notifications.addTemplate')}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
        width={600}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ channel_type: 'all', is_default: false }}>
          <Form.Item name="name" label={t('notifications.templateName')} rules={[{ required: true, message: t('notifications.templateNameRequired') }]}>
            <Input placeholder={t('notifications.templateNamePlaceholder')} />
          </Form.Item>
          <Form.Item name="channel_type" label={t('notifications.channelType')} rules={[{ required: true }]}>
            <Select options={CHANNEL_TYPES.map(v => ({ value: v, label: TYPE_LABEL_KEY[v] ? t(TYPE_LABEL_KEY[v]) : v }))} />
          </Form.Item>
          {/* 标题模板：仅 email 或 all 时显示 */}
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.channel_type !== cur.channel_type}>
            {({ getFieldValue }) => {
              const ct = getFieldValue('channel_type');
              return (ct === 'email' || ct === 'all') ? (
                <Form.Item name="subject_template" label={t('notifications.subjectTemplate')}>
                  <Input placeholder="[{severity}] {title}" />
                </Form.Item>
              ) : null;
            }}
          </Form.Item>
          <Form.Item name="body_template" label={t('notifications.bodyTemplate')} rules={[{ required: true, message: t('notifications.bodyTemplateRequired') }]}>
            <TextArea rows={6} placeholder={'告警: {title}\n级别: {severity}\n详情: {message}\n指标值: {metric_value}\n阈值: {threshold}\n主机: {host_id}\n触发时间: {fired_at}'} />
          </Form.Item>
          <Form.Item name="is_default" label={t('notifications.isDefault')} valuePropName="checked">
            <Switch />
          </Form.Item>
          <div style={{ background: '#f5f5f5', padding: '8px 12px', borderRadius: 6, fontSize: 12, color: '#666' }}>
            {t('notifications.availableVars')}{AVAILABLE_VARS.map(v => <Tag key={v} style={{ marginBottom: 4 }}>{v}</Tag>)}
          </div>
        </Form>
      </Modal>

      {/* 预览弹窗 */}
      <Modal title={t('notifications.previewTitle')} open={previewOpen} onCancel={() => setPreviewOpen(false)} footer={null} width={500}>
        {previewContent.subject && (
          <div style={{ marginBottom: 12 }}>
            <Typography.Text strong>{t('notifications.previewSubject')}</Typography.Text>
            <div style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4 }}>{previewContent.subject}</div>
          </div>
        )}
        <div>
          <Typography.Text strong>{t('notifications.previewBody')}</Typography.Text>
          <div style={{ background: '#f5f5f5', padding: 8, borderRadius: 4, marginTop: 4, whiteSpace: 'pre-wrap' }}>{previewContent.body}</div>
        </div>
      </Modal>
    </div>
  );
}
