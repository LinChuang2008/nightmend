/**
 * AI 洞察详情弹窗
 * 展示单条 AI 洞察的完整信息
 */
import { Modal, Tag, Typography, Descriptions, Space, Divider } from 'antd';
import { RobotOutlined, ExclamationCircleOutlined, InfoCircleOutlined, WarningOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import type { AIInsightItem } from '../../services/aiAnalysis';

const { Text, Paragraph } = Typography;

interface AIInsightDetailModalProps {
  open: boolean;
  insight: AIInsightItem | null;
  onClose: () => void;
}

const severityConfig: Record<string, { color: string; icon: React.ReactNode }> = {
  critical: { color: 'red', icon: <ExclamationCircleOutlined /> },
  warning: { color: 'orange', icon: <WarningOutlined /> },
  info: { color: 'blue', icon: <InfoCircleOutlined /> },
};

export default function AIInsightDetailModal({ open, insight, onClose }: AIInsightDetailModalProps) {
  const { t } = useTranslation();

  if (!insight) return null;

  const sev = severityConfig[insight.severity] || severityConfig.info;

  return (
    <Modal
      open={open}
      onCancel={onClose}
      footer={null}
      width={640}
      title={
        <Space>
          <RobotOutlined style={{ color: '#36cfc9' }} />
          <span>{t('aiAnalysis.insightDetail')}</span>
        </Space>
      }
    >
      <Descriptions column={2} size="small" style={{ marginBottom: 16 }}>
        <Descriptions.Item label={t('aiAnalysis.type')}>
          <Tag>{insight.insight_type}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label={t('aiAnalysis.severity')}>
          <Tag color={sev.color} icon={sev.icon}>{insight.severity}</Tag>
        </Descriptions.Item>
        <Descriptions.Item label={t('aiAnalysis.time')} span={2}>
          {insight.created_at ? new Date(insight.created_at).toLocaleString() : '-'}
        </Descriptions.Item>
      </Descriptions>

      <Text strong style={{ fontSize: 16, display: 'block', marginBottom: 8 }}>
        {insight.title}
      </Text>
      <Paragraph style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>
        {insight.summary}
      </Paragraph>

      {insight.details && (
        <>
          <Divider style={{ margin: '12px 0' }} />
          {insight.details.root_cause && (
            <div style={{ marginBottom: 12 }}>
              <Text strong>{t('aiAnalysis.rootCause')}：</Text>
              <Paragraph style={{ marginTop: 4 }}>{String(insight.details.root_cause)}</Paragraph>
            </div>
          )}
          {Array.isArray(insight.details.suggestions) && insight.details.suggestions.length > 0 && (
            <div style={{ marginBottom: 12 }}>
              <Text strong>{t('aiAnalysis.suggestions')}：</Text>
              <ul style={{ paddingLeft: 20, marginTop: 4 }}>
                {(insight.details.suggestions as string[]).map((s, i) => (
                  <li key={i}><Text>{s}</Text></li>
                ))}
              </ul>
            </div>
          )}
          {Array.isArray(insight.details.patterns) && insight.details.patterns.length > 0 && (
            <div>
              <Text strong>{t('aiAnalysis.patterns')}：</Text>
              <ul style={{ paddingLeft: 20, marginTop: 4 }}>
                {(insight.details.patterns as string[]).map((p, i) => (
                  <li key={i}><Text>{p}</Text></li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </Modal>
  );
}
