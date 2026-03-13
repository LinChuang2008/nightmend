/**
 * 通知渠道管理页面
 */
import { useEffect, useState } from 'react';
import { useResponsive } from '../hooks/useResponsive';
import { Table, Card, Typography, Button, Modal, Form, Input, InputNumber, Switch, Space, Select, Tag, message } from 'antd';
import { ExclamationCircleOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { notificationService } from '../services/alerts';
import type { NotificationChannel } from '../services/alerts';

const { TextArea } = Input;

const TYPE_TAG_COLOR: Record<string, string | undefined> = {
  webhook: undefined,
  email: 'blue',
  dingtalk: 'cyan',
  feishu: 'purple',
  wecom: 'green',
};

function buildConfig(type: string, values: Record<string, unknown>): Record<string, unknown> {
  switch (type) {
    case 'webhook':
      return {
        url: values.url,
        ...(values.headers ? { headers: JSON.parse(values.headers as string) } : {}),
      };
    case 'email':
      return {
        smtp_host: values.smtp_host,
        smtp_port: values.smtp_port,
        smtp_user: values.smtp_user,
        smtp_password: values.smtp_password,
        smtp_ssl: values.smtp_ssl,
        recipients: (values.recipients as string).split('\n').filter(Boolean),
      };
    case 'dingtalk':
      return {
        webhook_url: values.webhook_url,
        ...(values.secret ? { secret: values.secret } : {}),
      };
    case 'feishu':
      return {
        webhook_url: values.webhook_url,
        ...(values.secret ? { secret: values.secret } : {}),
      };
    case 'wecom':
      return { webhook_url: values.webhook_url };
    default:
      return {};
  }
}

function parseConfigToFields(type: string, config: Record<string, unknown>): Record<string, unknown> {
  switch (type) {
    case 'webhook':
      return {
        url: config.url,
        headers: config.headers ? JSON.stringify(config.headers, null, 2) : undefined,
      };
    case 'email':
      return {
        smtp_host: config.smtp_host,
        smtp_port: config.smtp_port,
        smtp_user: config.smtp_user,
        smtp_password: config.smtp_password,
        smtp_ssl: config.smtp_ssl,
        recipients: Array.isArray(config.recipients) ? (config.recipients as string[]).join('\n') : '',
      };
    case 'dingtalk':
    case 'feishu':
      return { webhook_url: config.webhook_url, secret: config.secret };
    case 'wecom':
      return { webhook_url: config.webhook_url };
    default:
      return {};
  }
}

export default function NotificationChannels() {
  const { t } = useTranslation();
  const { isMobile } = useResponsive();
  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(false);
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [form] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();

  const fetchList = async () => {
    setLoading(true);
    try {
      const { data } = await notificationService.listChannels();
      setChannels(Array.isArray(data) ? data : []);
    } catch { /* ignore */ } finally { setLoading(false); }
  };

  useEffect(() => { fetchList(); }, []);

  const openCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({ type: 'webhook', smtp_port: 465, smtp_ssl: true });
    setModalOpen(true);
  };

  const openEdit = (record: NotificationChannel) => {
    setEditing(record);
    const fields = parseConfigToFields(record.type, record.config);
    form.resetFields();
    form.setFieldsValue({ name: record.name, type: record.type, ...fields });
    setModalOpen(true);
  };

  const handleSubmit = async (values: Record<string, unknown>) => {
    const type = values.type as string;
    try {
      if (type === 'webhook' && values.headers) {
        JSON.parse(values.headers as string);
      }
    } catch {
      messageApi.error(t('notifications.headersInvalid'));
      return;
    }

    const config = buildConfig(type, values);
    try {
      if (editing) {
        await notificationService.updateChannel(editing.id, {
          name: values.name as string,
          type,
          config,
        });
        messageApi.success(t('notifications.updateSuccess'));
      } else {
        await notificationService.createChannel({
          name: values.name as string,
          type,
          config,
          is_enabled: true,
        });
        messageApi.success(t('notifications.createSuccess'));
      }
      setModalOpen(false);
      form.resetFields();
      fetchList();
    } catch { messageApi.error(editing ? t('notifications.updateFailed') : t('notifications.createFailed')); }
  };

  const handleToggle = async (record: NotificationChannel) => {
    try {
      await notificationService.updateChannel(record.id, { is_enabled: !record.is_enabled });
      messageApi.success(record.is_enabled ? t('notifications.disabledSuccess') : t('notifications.enabledSuccess'));
      fetchList();
    } catch { messageApi.error(t('notifications.actionFailed')); }
  };

  const handleDelete = (id: number) => {
    Modal.confirm({
      title: t('notifications.confirmDeleteChannel'),
      icon: <ExclamationCircleOutlined />,
      onOk: async () => {
        try {
          await notificationService.deleteChannel(id);
          messageApi.success(t('notifications.deletedSuccess'));
          fetchList();
        } catch { messageApi.error(t('notifications.deleteFailed')); }
      },
    });
  };

  const handleTestSend = async (r: NotificationChannel) => {
    messageApi.loading({ content: t('notifications.sendingTest'), key: 'testSend' });
    try {
      const response = await notificationService.testChannel(r.id);
      messageApi.success({
        content: response.data.message || t('notifications.testSendSuccess'),
        key: 'testSend',
        duration: 5,
      });
    } catch (error: unknown) {
      const errorMessage = error && typeof error === 'object' && 'response' in error
        ? ((error as { response: { data: { message: string } } }).response.data.message || t('notifications.testSendFailed'))
        : t('notifications.testSendFailed');
      messageApi.error({
        content: errorMessage,
        key: 'testSend',
        duration: 5,
      });
    }
  };

  const columns = [
    { title: 'ID', dataIndex: 'id', width: 60 },
    { title: t('notifications.channelName'), dataIndex: 'name' },
    {
      title: t('notifications.channelType'), dataIndex: 'type', width: 120,
      render: (val: string) => {
        const typeLabel: Record<string, string> = {
          webhook: t('notifications.typeWebhook'),
          email: t('notifications.typeEmail'),
          dingtalk: t('notifications.typeDingtalk'),
          feishu: t('notifications.typeFeishu'),
          wecom: t('notifications.typeWecom'),
        };
        return <Tag color={TYPE_TAG_COLOR[val]}>{typeLabel[val] || val}</Tag>;
      },
    },
    {
      title: t('notifications.enabled'), dataIndex: 'is_enabled', width: 80,
      render: (v: boolean, r: NotificationChannel) => (
        <Switch checked={v} onChange={() => handleToggle(r)} />
      ),
    },
    { title: t('common.createdAt'), dataIndex: 'created_at', render: (val: string) => new Date(val).toLocaleString() },
    {
      title: t('common.actions'), key: 'action', width: 220,
      render: (_: unknown, r: NotificationChannel) => (
        <Space>
          <Button type="link" size="small" onClick={() => handleTestSend(r)}>{t('notifications.testSend')}</Button>
          <Button type="link" size="small" onClick={() => openEdit(r)}>{t('common.edit')}</Button>
          <Button type="link" danger size="small" onClick={() => handleDelete(r.id)}>{t('common.delete')}</Button>
        </Space>
      ),
    },
  ];

  const renderConfigFields = (channelType: string) => {
    switch (channelType) {
      case 'webhook':
        return (
          <>
            <Form.Item name="url" label="Webhook URL" rules={[{ required: true, message: t('notifications.urlRequired') }, { type: 'url', message: t('notifications.urlInvalid') }]}>
              <Input placeholder="https://example.com/webhook" />
            </Form.Item>
            <Form.Item name="headers" label={t('notifications.headersJson')}>
              <TextArea rows={3} placeholder='{"Content-Type": "application/json"}' />
            </Form.Item>
          </>
        );
      case 'email':
        return (
          <>
            <Form.Item name="smtp_host" label={t('notifications.smtpServer')} rules={[{ required: true, message: t('notifications.smtpServerRequired') }]}>
              <Input placeholder="smtp.example.com" />
            </Form.Item>
            <Form.Item name="smtp_port" label={t('notifications.smtpPort')} rules={[{ required: true }]}>
              <InputNumber min={1} max={65535} style={{ width: '100%' }} />
            </Form.Item>
            <Form.Item name="smtp_user" label={t('notifications.smtpUser')} rules={[{ required: true, message: t('notifications.smtpUserRequired') }]}>
              <Input placeholder="user@example.com" />
            </Form.Item>
            <Form.Item name="smtp_password" label={t('notifications.smtpPassword')} rules={[{ required: true, message: t('notifications.smtpPasswordRequired') }]}>
              <Input.Password />
            </Form.Item>
            <Form.Item name="smtp_ssl" label={t('notifications.smtpSsl')} valuePropName="checked">
              <Switch />
            </Form.Item>
            <Form.Item name="recipients" label={t('notifications.recipients')} rules={[{ required: true, message: t('notifications.recipientsRequired') }]}>
              <TextArea rows={3} placeholder={'admin@example.com\nops@example.com'} />
            </Form.Item>
          </>
        );
      case 'dingtalk':
        return (
          <>
            <Form.Item name="webhook_url" label="Webhook URL" rules={[{ required: true, message: t('notifications.dingtalkUrlRequired') }]}>
              <Input placeholder="https://oapi.dingtalk.com/robot/send?access_token=..." />
            </Form.Item>
            <Form.Item name="secret" label={t('notifications.signSecret')}>
              <Input placeholder="SEC..." />
            </Form.Item>
          </>
        );
      case 'feishu':
        return (
          <>
            <Form.Item name="webhook_url" label="Webhook URL" rules={[{ required: true, message: t('notifications.feishuUrlRequired') }]}>
              <Input placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..." />
            </Form.Item>
            <Form.Item name="secret" label={t('notifications.signVerifySecret')}>
              <Input />
            </Form.Item>
          </>
        );
      case 'wecom':
        return (
          <Form.Item name="webhook_url" label="Webhook URL" rules={[{ required: true, message: t('notifications.wecomUrlRequired') }]}>
            <Input placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..." />
          </Form.Item>
        );
      default:
        return null;
    }
  };

  const channelTypeOptions = [
    { value: 'webhook', label: t('notifications.channelWebhook') },
    { value: 'email', label: t('notifications.channelEmail') },
    { value: 'dingtalk', label: t('notifications.channelDingtalk') },
    { value: 'feishu', label: t('notifications.channelFeishu') },
    { value: 'wecom', label: t('notifications.channelWecom') },
  ];

  return (
    <div>
      {contextHolder}
      <Typography.Title level={4}>{t('notifications.channels')}</Typography.Title>
      <Space style={{ marginBottom: 16 }}>
        <Button type="primary" onClick={openCreate}>{t('notifications.addChannel')}</Button>
      </Space>
      <Card>
        <Table dataSource={channels} columns={columns} rowKey="id" loading={loading} pagination={false} />
      </Card>

      <Modal
        title={editing ? t('notifications.editChannel') : t('notifications.addChannel')}
        open={modalOpen}
        onCancel={() => setModalOpen(false)}
        onOk={() => form.submit()}
        destroyOnClose
        width={isMobile ? '100%' : 560}
      >
        <Form form={form} layout="vertical" onFinish={handleSubmit} initialValues={{ type: 'webhook', smtp_port: 465, smtp_ssl: true }}>
          <Form.Item name="name" label={t('notifications.channelNameLabel')} rules={[{ required: true, message: t('notifications.nameRequired') }]}>
            <Input placeholder={t('notifications.channelExamplePlaceholder')} />
          </Form.Item>
          <Form.Item name="type" label={t('notifications.channelTypeLabel')} rules={[{ required: true }]}>
            <Select options={channelTypeOptions} disabled={!!editing} />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(prev, cur) => prev.type !== cur.type}>
            {({ getFieldValue }) => renderConfigFields(getFieldValue('type'))}
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
