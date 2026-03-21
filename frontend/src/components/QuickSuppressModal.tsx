/**
 * 快速屏蔽对话框组件 (Quick Suppress Modal Component)
 *
 * 用于快速创建屏蔽规则，屏蔽指定主机或服务的告警通知。
 */
import { useState } from 'react';
import { Modal, Input, Select, Form, message, Radio, Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { suppressionRuleService } from '../services/suppressionRules';

interface QuickSuppressModalProps {
  visible: boolean;
  onClose: () => void;
  onSuccess?: () => void;
  resourceType: 'host' | 'service';
  resourceId: number | string;
  resourceName?: string;
}

type DurationType = 'permanent' | 'preset' | 'custom';

export default function QuickSuppressModal({
  visible,
  onClose,
  onSuccess,
  resourceType,
  resourceId,
  resourceName,
}: QuickSuppressModalProps) {
  const { t } = useTranslation();
  const [form] = Form.useForm();
  const [loading, setLoading] = useState(false);
  const [durationType, setDurationType] = useState<DurationType>('preset');
  const [presetDuration, setPresetDuration] = useState<string>('24h');
  const [customHours, setCustomHours] = useState<number>(24);

  const handleOk = async () => {
    try {
      const values = await form.validateFields();
      setLoading(true);

      // 计算屏蔽时长
      let durationHours: number | null = null;

      if (durationType === 'preset') {
        if (presetDuration === '1h') durationHours = 1;
        else if (presetDuration === '24h') durationHours = 24;
        else if (presetDuration === '7d') durationHours = 24 * 7;
        else if (presetDuration === '30d') durationHours = 24 * 30;
      } else if (durationType === 'custom') {
        durationHours = customHours;
      }
      // permanent: durationHours 保持为 null

      await suppressionRuleService.quickSuppress({
        resource_type: resourceType,
        resource_id: typeof resourceId === 'string' ? parseInt(resourceId, 10) : resourceId,
        reason: values.reason || undefined,
        duration_hours: durationHours,
      });

      message.success(t('suppressionRules.quickSuppressSuccess'));
      form.resetFields();
      setPresetDuration('24h');
      setCustomHours(24);
      onSuccess?.();
      onClose();
    } catch (error: any) {
      console.error('Failed to create suppression rule:', error);
      message.error(t('suppressionRules.quickSuppressFailed'));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = () => {
    form.resetFields();
    setDurationType('preset');
    setPresetDuration('24h');
    setCustomHours(24);
    onClose();
  };

  return (
    <Modal
      title={t('suppressionRules.quickSuppressModalTitle')}
      open={visible}
      onOk={handleOk}
      onCancel={handleCancel}
      confirmLoading={loading}
      okText={t('suppressionRules.confirm')}
      cancelText={t('suppressionRules.cancel')}
    >
      <p style={{ marginBottom: 16, color: '#666' }}>
        {t('suppressionRules.quickSuppressModalDescription')}
      </p>
      {resourceName && (
        <p style={{ marginBottom: 16 }}>
          <strong>{resourceType === 'host' ? t('suppressionRules.resourceTypeHost') : t('suppressionRules.resourceTypeService')}:</strong> {resourceName}
        </p>
      )}

      <Form form={form} layout="vertical">
        <Form.Item label={t('suppressionRules.duration')} required>
          <Radio.Group
            value={durationType}
            onChange={(e) => setDurationType(e.target.value)}
            style={{ width: '100%' }}
          >
            <Space direction="vertical" style={{ width: '100%' }}>
              <Radio value="preset">
                {t('suppressionRules.presetDuration')}
              </Radio>
              {durationType === 'preset' && (
                <Select
                  style={{ width: '100%', marginLeft: 24 }}
                  value={presetDuration}
                  onChange={setPresetDuration}
                  options={[
                    { label: t('suppressionRules.duration1h'), value: '1h' },
                    { label: t('suppressionRules.duration24h'), value: '24h' },
                    { label: t('suppressionRules.duration7d'), value: '7d' },
                    { label: t('suppressionRules.duration30d'), value: '30d' },
                  ]}
                />
              )}

              <Radio value="custom">
                {t('suppressionRules.customDuration')}
              </Radio>
              {durationType === 'custom' && (
                <Input
                  type="number"
                  style={{ width: 200, marginLeft: 24 }}
                  value={customHours}
                  onChange={(e) => setCustomHours(Number(e.target.value))}
                  suffix={t('suppressionRules.durationHours')}
                  min={1}
                  max={8760}
                />
              )}

              <Radio value="permanent">
                {t('suppressionRules.permanent')}
              </Radio>
            </Space>
          </Radio.Group>
        </Form.Item>

        <Form.Item
          name="reason"
          label={t('suppressionRules.reason')}
        >
          <Input.TextArea
            rows={3}
            placeholder={t('suppressionRules.reasonPlaceholder')}
            maxLength={500}
            showCount
          />
        </Form.Item>
      </Form>
    </Modal>
  );
}
