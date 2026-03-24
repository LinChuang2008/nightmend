import { useEffect, useMemo, useState } from 'react';
import { Button, Card, Form, Input, InputNumber, Modal, Select, Space, Switch, Table, Tag, Typography, message, Popconfirm } from 'antd';
import PageHeader from '../components/PageHeader';
import { opsApi, type OpsAIConfig, type OpsAIConfigCreate, type OpsAIConfigUpdate, type OpsAIFeaturePolicy } from '../services/opsApi';

const CONTEXT_OPTIONS = [32000, 64000, 128000, 200000, 256000, 1000000];

export default function AIConfigs() {
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [open, setOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editing, setEditing] = useState<OpsAIConfig | null>(null);
  const [rows, setRows] = useState<OpsAIConfig[]>([]);
  const [features, setFeatures] = useState<OpsAIFeaturePolicy[]>([]);
  const [form] = Form.useForm();
  const [importForm] = Form.useForm();
  const [messageApi, contextHolder] = message.useMessage();

  const featureMap = useMemo(() => {
    const map = new Map<string, OpsAIFeaturePolicy>();
    features.forEach((f) => map.set(f.feature_key, f));
    return map;
  }, [features]);

  const load = async () => {
    setLoading(true);
    try {
      const [configs, featureDefs] = await Promise.all([
        opsApi.listAIConfigsAdmin(),
        opsApi.listAIConfigFeatures(),
      ]);
      setRows(configs);
      setFeatures(featureDefs);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const selectedFeatureKey = Form.useWatch('feature_key', form) as string | undefined;
  const isAssistant = selectedFeatureKey === 'ops_assistant';

  const assertFeatureLimit = (feature_key: string, skipId?: string) => {
    const policy = featureMap.get(feature_key);
    if (!policy) return;
    if (policy.max_models > 1) return;
    const count = rows.filter((r) => r.feature_key === feature_key && r.id !== skipId).length;
    if (count >= 1) {
      throw new Error(`${policy.label} 只能配置一个模型`);
    }
  };

  const onCreate = () => {
    setEditing(null);
    form.resetFields();
    form.setFieldsValue({
      feature_key: 'ops_assistant',
      model_context_tokens: 200000,
      allowed_context_tokens: 120000,
      max_output_tokens: 4000,
      enabled: true,
    });
    setOpen(true);
  };

  const onEdit = (row: OpsAIConfig) => {
    setEditing(row);
    form.setFieldsValue({
      feature_key: row.feature_key,
      name: row.name,
      base_url: row.base_url,
      model: row.model,
      api_key: '',
      model_context_tokens: row.model_context_tokens,
      allowed_context_tokens: row.allowed_context_tokens,
      max_output_tokens: row.max_output_tokens,
      extra_context: row.extra_context,
      enabled: row.enabled,
    });
    setOpen(true);
  };

  const onSave = async () => {
    const values = await form.validateFields();
    if (Number(values.allowed_context_tokens) > Number(values.model_context_tokens)) {
      messageApi.error('允许上下文不能大于模型上下文');
      return;
    }
    try {
      assertFeatureLimit(values.feature_key, editing?.id);
    } catch (e: any) {
      messageApi.error(e.message || '功能模型数量超限');
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        const payload: OpsAIConfigUpdate = { ...values };
        if (!String(payload.api_key || '').trim()) {
          delete payload.api_key;
        }
        await opsApi.updateAIConfig(editing.id, payload);
      } else {
        const payload: OpsAIConfigCreate = { ...values };
        if (!String(payload.api_key || '').trim()) {
          delete payload.api_key;
        }
        await opsApi.createAIConfig(payload);
      }
      setOpen(false);
      await load();
      messageApi.success('AI 配置已保存');
    } finally {
      setSaving(false);
    }
  };

  const openImport = () => {
    importForm.resetFields();
    importForm.setFieldsValue({ feature_key: 'ops_assistant' });
    setImportOpen(true);
  };

  const onImport = async () => {
    const values = await importForm.validateFields();
    try {
      assertFeatureLimit(values.feature_key);
      const config = JSON.parse(values.raw_json || '{}');
      await opsApi.importAIConfig(config, values.feature_key, values.name);
      setImportOpen(false);
      await load();
      messageApi.success('已导入 AI 配置');
    } catch (e: any) {
      messageApi.error(e?.message || '导入失败，请检查 JSON 格式');
    }
  };

  return (
    <div>
      {contextHolder}
      <PageHeader title="AI 配置中心（按功能模块）" />
      <Card>
        <Space style={{ marginBottom: 12 }}>
          <Button type="primary" onClick={onCreate}>新增功能模型配置</Button>
          <Button onClick={openImport}>导入 OpenAI JSON</Button>
          <Typography.Text type="secondary">建议先配置“默认配置（全局回退）”；除 AI 运维助手外，其他功能仅允许一个模型</Typography.Text>
        </Space>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={rows}
          pagination={false}
          columns={[
            { title: '功能模块', dataIndex: 'feature_key', render: (v: string) => featureMap.get(v)?.label || v },
            { title: '配置名称', dataIndex: 'name' },
            { title: '模型', dataIndex: 'model' },
            {
              title: 'API Key',
              render: (_, row: OpsAIConfig) => row.has_api_key
                ? <Tag color="green">{row.api_key_mask || '已配置'}</Tag>
                : <Tag>未配置</Tag>,
            },
            { title: '模型上下文', dataIndex: 'model_context_tokens' },
            { title: '允许上下文', dataIndex: 'allowed_context_tokens' },
            { title: '输出上限', dataIndex: 'max_output_tokens' },
            { title: '默认', dataIndex: 'is_default', render: (v: boolean) => v ? <Tag color="blue">默认</Tag> : '-' },
            { title: '启用', dataIndex: 'enabled', render: (v: boolean) => v ? <Tag color="green">启用</Tag> : <Tag>停用</Tag> },
            {
              title: '操作',
              render: (_, row: OpsAIConfig) => (
                <Space>
                  <Button size="small" onClick={() => onEdit(row)}>编辑</Button>
                  {!row.is_default && <Button size="small" onClick={async () => { await opsApi.setDefaultAIConfig(row.id); await load(); }}>设为默认</Button>}
                  {!row.is_default && (
                    <Popconfirm title="确认删除该配置？" onConfirm={async () => { await opsApi.deleteAIConfig(row.id); await load(); }}>
                      <Button size="small" danger>删除</Button>
                    </Popconfirm>
                  )}
                </Space>
              ),
            },
          ]}
        />
      </Card>

      <Modal
        title={editing ? '编辑功能模型配置' : '新增功能模型配置'}
        open={open}
        onCancel={() => setOpen(false)}
        onOk={onSave}
        confirmLoading={saving}
        width={760}
      >
        <Form form={form} layout="vertical">
          <Form.Item label="功能模块" name="feature_key" rules={[{ required: true }]}>
            <Select options={features.map((f) => ({ value: f.feature_key, label: `${f.label} (${f.feature_key})` }))} />
          </Form.Item>
          <Form.Item label="配置名称" name="name" rules={[{ required: true }]}>
            <Input placeholder="例如：AI 运维助手-主模型" />
          </Form.Item>
          <Form.Item label="Base URL" name="base_url" rules={[{ required: true }]}>
            <Input placeholder="https://api.openai.com/v1" />
          </Form.Item>
          <Form.Item label="Model" name="model" rules={[{ required: true }]}>
            <Input placeholder="gpt-5 / gpt-4.1 / deepseek-chat" />
          </Form.Item>
          <Form.Item label="API Key（留空则不更新）" name="api_key">
            <Input.Password />
          </Form.Item>
          {isAssistant && (
            <Form.Item label="模型上下文（Model Context）" name="model_context_tokens" rules={[{ required: true }]}>
              <Select options={CONTEXT_OPTIONS.map((v) => ({ value: v, label: `${v.toLocaleString()} tokens` }))} showSearch />
            </Form.Item>
          )}
          {!isAssistant && (
            <Form.Item label="模型上下文（Model Context）" name="model_context_tokens" rules={[{ required: true }]}>
              <InputNumber style={{ width: '100%' }} min={2048} max={1000000} />
            </Form.Item>
          )}
          <Form.Item label="允许上下文（Allowed Context）" name="allowed_context_tokens" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={2048} max={1000000} />
          </Form.Item>
          <Form.Item label="Max Output Tokens" name="max_output_tokens" rules={[{ required: true }]}>
            <InputNumber style={{ width: '100%' }} min={128} max={64000} />
          </Form.Item>
          {isAssistant && (
            <Form.Item label="额外上下文（仅助手预留）" name="extra_context">
              <Input.TextArea rows={4} />
            </Form.Item>
          )}
          {!isAssistant && (
            <Form.Item label="功能提示（可选）" name="extra_context">
              <Input.TextArea rows={2} />
            </Form.Item>
          )}
          <Form.Item label="启用" name="enabled" valuePropName="checked">
            <Switch />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title="导入 OpenAI 配置"
        open={importOpen}
        onCancel={() => setImportOpen(false)}
        onOk={onImport}
      >
        <Form form={importForm} layout="vertical">
          <Form.Item label="功能模块" name="feature_key" rules={[{ required: true }]}>
            <Select options={features.map((f) => ({ value: f.feature_key, label: `${f.label} (${f.feature_key})` }))} />
          </Form.Item>
          <Form.Item label="配置名称" name="name" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item label="OpenAI JSON" name="raw_json" rules={[{ required: true }]}>
            <Input.TextArea rows={8} placeholder='{"base_url":"https://api.openai.com/v1","api_key":"sk-...","model":"gpt-4.1","max_output_tokens":4000,"model_context_tokens":200000,"allowed_context_tokens":120000,"context":"..." }' />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
