/**
 * AI 日志分析弹窗
 * 调用后端 /ai/analyze-logs 实时分析异常日志并展示结果
 */
import { useState } from 'react';
import { Modal, Spin, Tag, Typography, Space, Alert, Divider, Result } from 'antd';
import { RobotOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { aiAnalysisApi, type LogAnalysisResult } from '../../services/aiAnalysis';

const { Text, Paragraph, Title } = Typography;

interface AILogAnalysisModalProps {
  open: boolean;
  onClose: () => void;
}

const severityColor: Record<string, string> = {
  critical: '#ff4d4f',
  warning: '#faad14',
  info: '#1677ff',
};

export default function AILogAnalysisModal({ open, onClose }: AILogAnalysisModalProps) {
  const { t } = useTranslation();
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<LogAnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const doAnalyze = async () => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const { data } = await aiAnalysisApi.analyzeLogs(1);
      setResult(data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleOpen = () => {
    if (!result && !loading) {
      doAnalyze();
    }
  };

  return (
    <Modal
      open={open}
      onCancel={() => { onClose(); setResult(null); setError(null); }}
      footer={null}
      width={640}
      title={
        <Space>
          <RobotOutlined style={{ color: '#36cfc9' }} />
          <span>{t('aiAnalysis.logAnalysisTitle')}</span>
        </Space>
      }
      afterOpenChange={(visible) => { if (visible) handleOpen(); }}
    >
      {loading && (
        <div style={{ textAlign: 'center', padding: '48px 0' }}>
          <Spin size="large" />
          <div style={{ marginTop: 16 }}>
            <Text type="secondary">{t('aiAnalysis.analyzing')}</Text>
          </div>
        </div>
      )}

      {error && (
        <Alert
          type="error"
          message={t('aiAnalysis.analysisFailed')}
          description={error}
          showIcon
          style={{ marginBottom: 16 }}
        />
      )}

      {result && !loading && (
        <>
          {result.log_count === 0 ? (
            <Result
              icon={<ThunderboltOutlined style={{ color: '#52c41a' }} />}
              title={t('aiAnalysis.noAbnormalLogs')}
              subTitle={result.summary}
            />
          ) : (
            <>
              <div style={{ marginBottom: 16, display: 'flex', gap: 12, alignItems: 'center' }}>
                <Tag color={severityColor[result.severity] ? result.severity : 'blue'}>
                  {result.severity.toUpperCase()}
                </Tag>
                <Text type="secondary">
                  {t('aiAnalysis.analyzedLogs', { count: result.log_count })}
                </Text>
              </div>

              <Title level={5} style={{ marginBottom: 8 }}>{result.title}</Title>
              <Paragraph style={{ whiteSpace: 'pre-wrap', lineHeight: 1.8 }}>
                {result.summary}
              </Paragraph>

              {result.patterns?.length > 0 && (
                <>
                  <Divider style={{ margin: '12px 0' }} />
                  <Text strong>{t('aiAnalysis.patterns')}：</Text>
                  <ul style={{ paddingLeft: 20, marginTop: 4 }}>
                    {result.patterns.map((p, i) => (
                      <li key={i}><Text>{p}</Text></li>
                    ))}
                  </ul>
                </>
              )}

              {result.suggestions?.length > 0 && (
                <>
                  <Divider style={{ margin: '12px 0' }} />
                  <Text strong>{t('aiAnalysis.suggestions')}：</Text>
                  <ul style={{ paddingLeft: 20, marginTop: 4 }}>
                    {result.suggestions.map((s, i) => (
                      <li key={i}><Text>{s}</Text></li>
                    ))}
                  </ul>
                </>
              )}
            </>
          )}
        </>
      )}
    </Modal>
  );
}
