/**
 * AI 智能分析页面
 *
 * 包含三大功能区域：
 * 1. 系统概况卡片 - 展示主机、服务、告警、错误日志数量及平均 CPU/内存使用率
 * 2. AI 对话 - 用户可通过自然语言向 AI 提问系统运行状况
 * 3. AI 洞察列表 - 展示 AI 自动分析产生的异常检测、根因分析等结果
 */
import { useEffect, useState, useRef } from 'react';
import { Row, Col, Card, Statistic, Typography, Tag, Table, Button, Input, Space, Select, Progress, Collapse, Spin, message, Tooltip, Rate } from 'antd';
import {
  CloudServerOutlined,
  ApiOutlined,
  AlertOutlined,
  FileTextOutlined,
  SendOutlined,
  RobotOutlined,
  UserOutlined,
  ThunderboltOutlined,
  LikeOutlined,
  DislikeOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import dayjs from 'dayjs';
import api, { aiApi } from '../services/api';
import { aiFeedbackService } from '../services/aiFeedback';

const { Title, Text, Paragraph } = Typography;

interface SystemSummaryRaw {
  hosts: { total: number; online: number; offline: number };
  services: { total: number; up: number; down: number };
  recent_1h: { alert_count: number; error_log_count: number };
  avg_usage: { cpu_percent: number; memory_percent: number };
}

interface SystemSummary {
  total_hosts: number;
  online_hosts: number;
  offline_hosts: number;
  total_services: number;
  healthy_services: number;
  unhealthy_services: number;
  alerts_1h: number;
  error_logs_1h: number;
  avg_cpu: number;
  avg_memory: number;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'ai';
  content: string;
  isError?: boolean;
  sources?: Array<{ type: string; summary: string }>;
  memory_context?: Array<Record<string, any>>;
  timestamp: number;
}

interface InsightItem {
  id: number;
  insight_type: string;
  severity: string;
  title: string;
  summary: string;
  details: any;
  related_host_id: number | null;
  status: string;
  created_at: string;
}

const severityColor: Record<string, string> = { critical: 'red', high: 'orange', warning: 'gold', medium: 'orange', low: 'blue', info: 'blue' };

export default function AIAnalysis() {
  const { t } = useTranslation();

  const insightTypeLabel: Record<string, string> = {
    anomaly: t('aiAnalysis.insightTypeAnomaly'),
    root_cause: t('aiAnalysis.insightTypeRootCause'),
    chat: t('aiAnalysis.insightTypeChat'),
    trend: t('aiAnalysis.insightTypeTrend'),
  };

  const quickQuestions = [
    t('aiAnalysis.quickQuestions.healthStatus'),
    t('aiAnalysis.quickQuestions.recentAnomalies'),
    t('aiAnalysis.quickQuestions.performanceTrend'),
  ];

  const [summary, setSummary] = useState<SystemSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatInput, setChatInput] = useState('');
  const [chatLoading, setChatLoading] = useState(false);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [messageFeedback, setMessageFeedback] = useState<Record<string, { rating?: number; helpful?: boolean }>>({});

  const handleQuickFeedback = async (messageId: string, msg: ChatMessage, isHelpful: boolean) => {
    if (msg.role !== 'ai') return;
    setFeedbackLoading(true);
    try {
      await aiFeedbackService.quickFeedback({
        ai_response: msg.content,
        rating: isHelpful ? 4 : 2,
        is_helpful: isHelpful
      });
      setMessageFeedback(prev => ({ ...prev, [messageId]: { helpful: isHelpful } }));
      messageApi.success(t('aiAnalysis.feedbackSubmitted'));
    } catch {
      messageApi.error(t('aiAnalysis.feedbackFailed'));
    } finally {
      setFeedbackLoading(false);
    }
  };

  const handleRatingFeedback = async (messageId: string, msg: ChatMessage, rating: number) => {
    if (msg.role !== 'ai' || rating === 0) return;
    setFeedbackLoading(true);
    try {
      await aiFeedbackService.quickFeedback({
        ai_response: msg.content,
        rating: rating,
        is_helpful: rating >= 3
      });
      setMessageFeedback(prev => ({ ...prev, [messageId]: { rating: rating, helpful: rating >= 3 } }));
      messageApi.success(t('aiAnalysis.ratingSubmitted'));
    } catch {
      messageApi.error(t('aiAnalysis.ratingFailed'));
    } finally {
      setFeedbackLoading(false);
    }
  };

  const chatEndRef = useRef<HTMLDivElement>(null);
  const [insights, setInsights] = useState<InsightItem[]>([]);
  const [insightsTotal, setInsightsTotal] = useState(0);
  const [insightsLoading, setInsightsLoading] = useState(true);
  const [insightsPage, setInsightsPage] = useState(1);
  const [insightSeverity, setInsightSeverity] = useState<string>('');
  const [insightStatus, setInsightStatus] = useState<string>('');
  const [analyzeLoading, setAnalyzeLoading] = useState(false);

  const [messageApi, contextHolder] = message.useMessage();

  const fetchSummary = async () => {
    setSummaryLoading(true);
    try {
      const { data } = await api.get<SystemSummaryRaw>('/ai/system-summary');
      setSummary({
        total_hosts: data.hosts?.total ?? 0,
        online_hosts: data.hosts?.online ?? 0,
        offline_hosts: data.hosts?.offline ?? 0,
        total_services: data.services?.total ?? 0,
        healthy_services: data.services?.up ?? 0,
        unhealthy_services: data.services?.down ?? 0,
        alerts_1h: data.recent_1h?.alert_count ?? 0,
        error_logs_1h: data.recent_1h?.error_log_count ?? 0,
        avg_cpu: data.avg_usage?.cpu_percent ?? 0,
        avg_memory: data.avg_usage?.memory_percent ?? 0,
      });
    } catch { /* ignore */ } finally { setSummaryLoading(false); }
  };

  const fetchInsights = async () => {
    setInsightsLoading(true);
    try {
      const params: Record<string, unknown> = { page: insightsPage, page_size: 10 };
      if (insightSeverity) params.severity = insightSeverity;
      if (insightStatus) params.status = insightStatus;
      const { data } = await api.get('/ai/insights', { params });
      setInsights(data.items || []);
      setInsightsTotal(data.total || 0);
    } catch { /* ignore */ } finally { setInsightsLoading(false); }
  };

  useEffect(() => { fetchSummary(); }, []);
  useEffect(() => { fetchInsights(); }, [insightsPage, insightSeverity, insightStatus]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendChat = async (question: string) => {
    if (!question.trim()) return;
    const q = question.trim();
    setChatInput('');
    const userMessage: ChatMessage = {
      id: `user_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      role: 'user',
      content: q,
      timestamp: Date.now()
    };
    setMessages(prev => [...prev, userMessage]);
    setChatLoading(true);
    try {
      const { data } = await aiApi.post('/ai/chat', { question: q });
      const aiMessage: ChatMessage = {
        id: `ai_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
        role: 'ai',
        content: data.answer,
        sources: data.sources,
        memory_context: data.memory_context,
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, aiMessage]);
    } catch {
      const errorMessage: ChatMessage = {
        id: `ai_error_${Date.now()}`,
        role: 'ai',
        isError: true,
        content: t('aiAnalysis.aiUnavailable'),
        timestamp: Date.now()
      };
      setMessages(prev => [...prev, errorMessage]);
    } finally { setChatLoading(false); }
  };

  const handleAnalyze = async () => {
    setAnalyzeLoading(true);
    try {
      await aiApi.post('/ai/analyze-logs', { hours: 1 });
      messageApi.success(t('aiAnalysis.analyzeSuccess'));
      fetchInsights();
    } catch {
      messageApi.error(t('aiAnalysis.analyzeFailed'));
    } finally { setAnalyzeLoading(false); }
  };

  const insightColumns = [
    {
      title: t('aiAnalysis.insightTime'), dataIndex: 'created_at', width: 170,
      render: (val: string) => dayjs(val).format('YYYY-MM-DD HH:mm:ss'),
    },
    {
      title: t('aiAnalysis.insightType'), dataIndex: 'insight_type', width: 100,
      render: (val: string) => <Tag>{insightTypeLabel[val] || val}</Tag>,
    },
    {
      title: t('aiAnalysis.insightSeverity'), dataIndex: 'severity', width: 90,
      render: (s: string) => <Tag color={severityColor[s] || 'default'}>{s}</Tag>,
    },
    { title: t('aiAnalysis.insightTitle'), dataIndex: 'title', ellipsis: true },
    {
      title: t('aiAnalysis.insightStatus'), dataIndex: 'status', width: 80,
      render: (s: string) => <Tag color={s === 'resolved' ? 'green' : s === 'new' ? 'blue' : 'default'}>{s}</Tag>,
    },
  ];

  return (
    <div>
      {contextHolder}
      <Title level={4}><RobotOutlined /> {t('aiAnalysis.title')}</Title>

      {/* 系统概况统计卡片 - 紧凑布局 */}
      <Spin spinning={summaryLoading}>
        <Row gutter={[12, 12]}>
          <Col xs={24} sm={12} md={6}>
            <Card size="small" style={{ background: 'linear-gradient(45deg, #f6ffed, #ffffff)' }}>
              <Statistic title={t('aiAnalysis.hosts')} value={summary?.online_hosts ?? '-'} suffix={`/ ${summary?.total_hosts ?? '-'}`} prefix={<CloudServerOutlined style={{ color: '#52c41a' }} />} />
              <Text type="secondary" style={{ fontSize: 12 }}>{t('aiAnalysis.onlineTotal')}</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small" style={{ background: 'linear-gradient(45deg, #f0f9ff, #ffffff)' }}>
              <Statistic title={t('aiAnalysis.services')} value={summary?.healthy_services ?? '-'} suffix={`/ ${summary?.total_services ?? '-'}`} prefix={<ApiOutlined style={{ color: '#1677ff' }} />} />
              <Text type="secondary" style={{ fontSize: 12 }}>{t('aiAnalysis.healthyTotal')}</Text>
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small" style={{ background: 'linear-gradient(45deg, #fff2e8, #ffffff)' }}>
              <Statistic title={t('aiAnalysis.alerts1h')} value={summary?.alerts_1h ?? '-'} prefix={<AlertOutlined style={{ color: '#faad14' }} />}
                valueStyle={{ color: (summary?.alerts_1h ?? 0) > 0 ? '#cf1322' : '#3f8600' }} />
            </Card>
          </Col>
          <Col xs={24} sm={12} md={6}>
            <Card size="small" style={{ background: 'linear-gradient(45deg, #fff1f0, #ffffff)' }}>
              <Statistic title={t('aiAnalysis.errorLogs1h')} value={summary?.error_logs_1h ?? '-'} prefix={<FileTextOutlined style={{ color: '#ff4d4f' }} />}
                valueStyle={{ color: (summary?.error_logs_1h ?? 0) > 0 ? '#cf1322' : '#3f8600' }} />
            </Card>
          </Col>
        </Row>
        {summary && (
          <Row gutter={[12, 12]} style={{ marginTop: 12 }}>
            <Col xs={12} sm={6}>
              <Card size="small" style={{ textAlign: 'center', background: 'linear-gradient(135deg, #e6f7ff, #ffffff)' }}>
                <Progress type="circle" percent={Math.round(summary.avg_cpu)} size={70}
                  strokeColor={summary.avg_cpu > 80 ? '#ff4d4f' : summary.avg_cpu > 60 ? '#faad14' : '#52c41a'} strokeWidth={8} />
                <div style={{ marginTop: 6 }}><Text type="secondary" style={{ fontSize: 11 }}>{t('aiAnalysis.avgCpu')}</Text></div>
              </Card>
            </Col>
            <Col xs={12} sm={6}>
              <Card size="small" style={{ textAlign: 'center', background: 'linear-gradient(135deg, #f6ffed, #ffffff)' }}>
                <Progress type="circle" percent={Math.round(summary.avg_memory)} size={70}
                  strokeColor={summary.avg_memory > 80 ? '#ff4d4f' : summary.avg_memory > 60 ? '#faad14' : '#52c41a'} strokeWidth={8} />
                <div style={{ marginTop: 6 }}><Text type="secondary" style={{ fontSize: 11 }}>{t('aiAnalysis.avgMemory')}</Text></div>
              </Card>
            </Col>
          </Row>
        )}
      </Spin>

      {/* AI 对话区域 */}
      <Card title={<><RobotOutlined /> {t('aiAnalysis.aiChat')}</>} style={{ marginTop: 16 }}>
        <div style={{
          background: '#f5f7fa', borderRadius: 8, padding: 16, minHeight: 200, maxHeight: 400, overflowY: 'auto', marginBottom: 16,
        }}>
          {messages.length === 0 && (
            <div style={{ textAlign: 'center', padding: '24px 20px', position: 'relative' }}>
              {/* 品牌机器人头像 */}
              <div style={{
                width: 80, height: 80, margin: '0 auto 16px',
                background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: '0 4px 20px rgba(102, 126, 234, 0.3)'
              }}>
                <RobotOutlined style={{ fontSize: 36, color: '#fff' }} />
              </div>
              <Title level={4} style={{ margin: '0 0 8px 0', color: '#262626' }}>VigilOps AI 助手</Title>
              <Text type="secondary" style={{ display: 'block', marginBottom: 24, fontSize: 14 }}>
                {t('aiAnalysis.askAI')} 我可以帮您分析系统状态、诊断问题
              </Text>
              
              {/* 预设问题卡片 */}
              <Row gutter={[12, 12]} justify="center">
                {[
                  { text: '系统整体健康状况如何？', icon: <AlertOutlined />, color: '#52c41a' },
                  { text: '最近有哪些异常？', icon: <FileTextOutlined />, color: '#faad14' },
                  { text: 'CPU 使用率趋势分析', icon: <CloudServerOutlined />, color: '#1677ff' },
                ].map((item, idx) => (
                  <Col xs={24} sm={8} key={idx}>
                    <Card
                      size="small"
                      hoverable
                      onClick={() => sendChat(item.text)}
                      style={{
                        border: `1px solid ${item.color}20`,
                        background: `linear-gradient(45deg, ${item.color}08, #ffffff)`,
                        cursor: 'pointer',
                        transition: 'all 0.3s ease'
                      }}
                      bodyStyle={{ padding: '12px' }}
                    >
                      <div style={{ textAlign: 'center' }}>
                        <div style={{ color: item.color, fontSize: 18, marginBottom: 6 }}>
                          {item.icon}
                        </div>
                        <Text style={{ fontSize: 13, fontWeight: 500 }}>{item.text}</Text>
                      </div>
                    </Card>
                  </Col>
                ))}
              </Row>
            </div>
          )}
          {messages.map((msg) => (
            <div key={msg.id} style={{
              display: 'flex', justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start', marginBottom: 12,
            }}>
              <div style={{
                maxWidth: '70%',
                padding: '10px 14px',
                borderRadius: 12,
                background: msg.role === 'user' ? '#1677ff' : '#fff',
                color: msg.role === 'user' ? '#fff' : '#333',
                border: msg.role === 'ai' ? '1px solid #e8e8e8' : 'none',
                boxShadow: '0 1px 2px rgba(0,0,0,0.06)',
              }}>
                <div style={{ marginBottom: 4 }}>
                  {msg.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
                  <Text style={{ marginLeft: 6, color: msg.role === 'user' ? '#fff' : '#666', fontSize: 12 }}>
                    {msg.role === 'user' ? t('aiAnalysis.youLabel') : t('aiAnalysis.aiAssistant')}
                  </Text>
                </div>
                <Paragraph style={{ margin: 0, color: msg.role === 'user' ? '#fff' : '#333', whiteSpace: 'pre-wrap' }}>
                  {msg.content}
                </Paragraph>
                {msg.sources && msg.sources.length > 0 && (
                  <Collapse ghost style={{ marginTop: 8 }} items={[{
                    key: '1',
                    label: <Text type="secondary" style={{ fontSize: 12 }}>{t('aiAnalysis.referenceSources', { count: msg.sources.length })}</Text>,
                    children: msg.sources.map((s, j) => (
                      <div key={j} style={{ fontSize: 12, color: '#666', marginBottom: 4 }}>
                        <Tag>{s.type}</Tag> {s.summary}
                      </div>
                    )),
                  }]} />
                )}
                {msg.memory_context && msg.memory_context.length > 0 && (
                  <Collapse ghost style={{ marginTop: 4 }} items={[{
                    key: 'memory',
                    label: <Text type="secondary" style={{ fontSize: 12 }}>📚 {t('aiAnalysis.historyContext', { count: msg.memory_context.length })}</Text>,
                    children: msg.memory_context.map((mem, j) => (
                      <div key={j} style={{ fontSize: 12, color: '#666', marginBottom: 4, padding: '4px 8px', background: '#f9f9f9', borderRadius: 4 }}>
                        {mem.content || mem.text || JSON.stringify(mem)}
                      </div>
                    )),
                  }]} />
                )}

                {msg.role === 'ai' && !msg.isError && (
                  <div style={{
                    marginTop: 8,
                    paddingTop: 8,
                    borderTop: '1px solid #f0f0f0',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    fontSize: 12
                  }}>
                    <Text type="secondary" style={{ fontSize: 12 }}>{t('aiAnalysis.helpful')}</Text>
                    <Space size="small">
                      <Tooltip title={t('aiAnalysis.useful')}>
                        <Button
                          size="small"
                          type={messageFeedback[msg.id]?.helpful === true ? 'primary' : 'text'}
                          icon={<LikeOutlined />}
                          onClick={() => handleQuickFeedback(msg.id, msg, true)}
                          loading={feedbackLoading}
                          disabled={messageFeedback[msg.id]?.helpful !== undefined}
                        >
                          {t('aiAnalysis.useful')}
                        </Button>
                      </Tooltip>
                      <Tooltip title={t('aiAnalysis.useless')}>
                        <Button
                          size="small"
                          type={messageFeedback[msg.id]?.helpful === false ? 'primary' : 'text'}
                          icon={<DislikeOutlined />}
                          onClick={() => handleQuickFeedback(msg.id, msg, false)}
                          loading={feedbackLoading}
                          disabled={messageFeedback[msg.id]?.helpful !== undefined}
                        >
                          {t('aiAnalysis.useless')}
                        </Button>
                      </Tooltip>
                      <Rate
                        size="small"
                        value={messageFeedback[msg.id]?.rating || 0}
                        onChange={(rating) => handleRatingFeedback(msg.id, msg, rating)}
                        disabled={messageFeedback[msg.id]?.rating !== undefined || feedbackLoading}
                        style={{ fontSize: 14 }}
                      />
                    </Space>
                  </div>
                )}
              </div>
            </div>
          ))}
          {chatLoading && (
            <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 12 }}>
              <div style={{ padding: '10px 14px', borderRadius: 12, background: '#fff', border: '1px solid #e8e8e8' }}>
                <Spin size="small" /> <Text type="secondary">{t('aiAnalysis.aiThinking')}</Text>
              </div>
            </div>
          )}
          <div ref={chatEndRef} />
        </div>
        <div style={{ marginBottom: 12 }}>
          <Text type="secondary" style={{ fontSize: 12, display: 'block', marginBottom: 8 }}>💡 快速问题:</Text>
          <Row gutter={[8, 8]}>
            {quickQuestions.map((q, idx) => (
              <Col key={q} flex="auto">
                <Button 
                  size="small" 
                  type="dashed"
                  icon={<ThunderboltOutlined />} 
                  onClick={() => sendChat(q)} 
                  disabled={chatLoading}
                  block
                  style={{ 
                    height: 32,
                    borderColor: ['#52c41a', '#faad14', '#1677ff'][idx % 3],
                    color: ['#52c41a', '#faad14', '#1677ff'][idx % 3],
                    fontSize: 12
                  }}
                >
                  {q}
                </Button>
              </Col>
            ))}
          </Row>
        </div>
        <Input.Search
          placeholder={t('aiAnalysis.chatPlaceholder')}
          enterButton={<><SendOutlined /> {t('aiAnalysis.sendButton')}</>}
          value={chatInput}
          onChange={e => setChatInput(e.target.value)}
          onSearch={sendChat}
          loading={chatLoading}
          size="large"
        />
      </Card>

      {/* AI 洞察列表 */}
      <Card title={t('aiAnalysis.insightList')} style={{ marginTop: 16 }}
        extra={
          <Button type="primary" icon={<ThunderboltOutlined />} loading={analyzeLoading} onClick={handleAnalyze}>
            {t('aiAnalysis.triggerAnalysis')}
          </Button>
        }
      >
        <Row style={{ marginBottom: 16 }}>
          <Space>
            <Select placeholder={t('aiAnalysis.filterSeverity')} allowClear style={{ width: 120 }}
              onChange={v => { setInsightSeverity(v || ''); setInsightsPage(1); }}
              options={[
                { label: 'Critical', value: 'critical' },
                { label: 'High', value: 'high' },
                { label: 'Medium', value: 'medium' },
                { label: 'Low', value: 'low' },
                { label: 'Info', value: 'info' },
              ]}
            />
            <Select placeholder={t('aiAnalysis.filterStatus')} allowClear style={{ width: 120 }}
              onChange={v => { setInsightStatus(v || ''); setInsightsPage(1); }}
              options={[
                { label: t('aiAnalysis.insightNew'), value: 'new' },
                { label: t('aiAnalysis.insightAcknowledged'), value: 'acknowledged' },
                { label: t('aiAnalysis.insightResolved'), value: 'resolved' },
              ]}
            />
          </Space>
        </Row>
        <Table
          dataSource={insights}
          columns={insightColumns}
          rowKey="id"
          loading={insightsLoading}
          pagination={{ current: insightsPage, pageSize: 10, total: insightsTotal, onChange: p => setInsightsPage(p) }}
          expandable={{
            expandedRowRender: (record: InsightItem) => (
              <div style={{ padding: '8px 0' }}>
                <Paragraph><strong>{t('aiAnalysis.insightSummaryLabel')}</strong>{record.summary}</Paragraph>
                {record.details && (
                  <Paragraph>
                    <strong>{t('aiAnalysis.insightDetailsLabel')}</strong>
                    <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 12, maxHeight: 300, overflow: 'auto' }}>
                      {typeof record.details === 'string' ? record.details : JSON.stringify(record.details, null, 2)}
                    </pre>
                  </Paragraph>
                )}
              </div>
            ),
          }}
        />
      </Card>
    </div>
  );
}
