/**
 * Landing Page - 产品首页
 * 未登录用户的默认入口，展示产品价值、核心特性和CTA
 */
import { useNavigate } from 'react-router-dom';
import { Button, Card, Typography, Row, Col, Space, Table, Tag, Image } from 'antd';
import {
  RobotOutlined,
  ThunderboltOutlined,
  ApiOutlined,
  CheckCircleOutlined,
  CloseCircleOutlined,
  ArrowRightOutlined,
  SafetyCertificateOutlined,
  DashboardOutlined,
  GlobalOutlined,
} from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useTheme } from '../contexts/ThemeContext';

const { Title, Paragraph, Text } = Typography;

/** 竞品对比数据 */
const comparisonColumns = (t: (key: string) => string) => [
  { title: t('landing.comparison.feature'), dataIndex: 'feature', key: 'feature', width: 200 },
  {
    title: 'VigilOps',
    dataIndex: 'vigilops',
    key: 'vigilops',
    render: (v: boolean) =>
      v ? <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} /> : <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />,
  },
  {
    title: 'Datadog',
    dataIndex: 'datadog',
    key: 'datadog',
    render: (v: boolean) =>
      v ? <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} /> : <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />,
  },
  {
    title: 'Grafana',
    dataIndex: 'grafana',
    key: 'grafana',
    render: (v: boolean) =>
      v ? <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} /> : <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />,
  },
  {
    title: 'Zabbix',
    dataIndex: 'zabbix',
    key: 'zabbix',
    render: (v: boolean) =>
      v ? <CheckCircleOutlined style={{ color: '#52c41a', fontSize: 18 }} /> : <CloseCircleOutlined style={{ color: '#ff4d4f', fontSize: 18 }} />,
  },
];

const comparisonData = (t: (key: string) => string) => [
  { key: '1', feature: t('landing.comparison.aiAnalysis'), vigilops: true, datadog: true, grafana: false, zabbix: false },
  { key: '2', feature: t('landing.comparison.autoRemediation'), vigilops: true, datadog: false, grafana: false, zabbix: false },
  { key: '3', feature: t('landing.comparison.mcpIntegration'), vigilops: true, datadog: false, grafana: false, zabbix: false },
  { key: '4', feature: t('landing.comparison.topologyVisualization'), vigilops: true, datadog: true, grafana: false, zabbix: true },
  { key: '5', feature: t('landing.comparison.slaManagement'), vigilops: true, datadog: true, grafana: false, zabbix: true },
  { key: '6', feature: t('landing.comparison.selfHosted'), vigilops: true, datadog: false, grafana: true, zabbix: true },
  { key: '7', feature: t('landing.comparison.openSource'), vigilops: true, datadog: false, grafana: true, zabbix: true },
];

export default function Landing() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { isDark } = useTheme();

  return (
    <div style={{ minHeight: '100vh', background: isDark ? '#141414' : '#fff' }}>
      {/* Navbar */}
      <div
        style={{
          position: 'sticky',
          top: 0,
          zIndex: 100,
          padding: '0 48px',
          height: 64,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          background: isDark ? 'rgba(20,20,20,0.9)' : 'rgba(255,255,255,0.9)',
          backdropFilter: 'blur(8px)',
          borderBottom: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'}`,
        }}
      >
        <Space align="center">
          <SafetyCertificateOutlined style={{ fontSize: 28, color: '#1677ff' }} />
          <Text strong style={{ fontSize: 20, color: isDark ? '#fff' : '#000' }}>VigilOps</Text>
          <Tag color="blue" style={{ marginLeft: 8 }}>v2026.03.14</Tag>
        </Space>
        <Space>
          <Button type="text" href="https://github.com/lchuangnet/vigilops" target="_blank" rel="noopener noreferrer">
            GitHub
          </Button>
          <Button type="primary" onClick={() => navigate('/login')}>
            {t('landing.signIn')}
          </Button>
        </Space>
      </div>

      {/* Hero Section */}
      <div
        style={{
          textAlign: 'center',
          padding: '100px 24px 80px',
          background: isDark
            ? 'linear-gradient(180deg, #141414 0%, #1a1a2e 100%)'
            : 'linear-gradient(180deg, #f0f5ff 0%, #ffffff 100%)',
        }}
      >
        <Tag color="blue" style={{ marginBottom: 24, fontSize: 14, padding: '4px 16px' }}>
          {t('landing.heroTag')}
        </Tag>
        <Title
          level={1}
          style={{
            fontSize: 48,
            fontWeight: 800,
            maxWidth: 800,
            margin: '0 auto 24px',
            lineHeight: 1.2,
            color: isDark ? '#fff' : '#000',
          }}
        >
          {t('landing.heroTitle')}
        </Title>
        <Paragraph
          style={{
            fontSize: 20,
            maxWidth: 640,
            margin: '0 auto 48px',
            color: isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.65)',
          }}
        >
          {t('landing.heroDescription')}
        </Paragraph>
        <Space size="large">
          <Button type="primary" size="large" icon={<ArrowRightOutlined />} onClick={() => navigate('/login')}>
            {t('landing.getStarted')}
          </Button>
          <Button
            size="large"
            href="https://github.com/lchuangnet/vigilops"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('landing.viewDocs')}
          </Button>
        </Space>

        {/* Dashboard screenshot */}
        <div style={{ maxWidth: 960, margin: '64px auto 0', borderRadius: 12, overflow: 'hidden', boxShadow: '0 20px 60px rgba(0,0,0,0.15)' }}>
          <Image
            src="/screenshots/dashboard.jpg"
            alt="VigilOps Dashboard"
            preview={false}
            style={{ width: '100%', display: 'block' }}
            fallback="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='960' height='540' fill='%23f0f0f0'%3E%3Crect width='960' height='540'/%3E%3Ctext x='480' y='270' text-anchor='middle' fill='%23999' font-size='24'%3EVigilOps Dashboard%3C/text%3E%3C/svg%3E"
          />
        </div>
      </div>

      {/* Feature Cards */}
      <div style={{ maxWidth: 1200, margin: '0 auto', padding: '80px 24px' }}>
        <Title level={2} style={{ textAlign: 'center', marginBottom: 16, color: isDark ? '#fff' : '#000' }}>
          {t('landing.featuresTitle')}
        </Title>
        <Paragraph style={{ textAlign: 'center', marginBottom: 64, fontSize: 16, color: isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.45)' }}>
          {t('landing.featuresSubtitle')}
        </Paragraph>
        <Row gutter={[32, 32]}>
          {[
            {
              icon: <RobotOutlined style={{ fontSize: 40, color: '#1677ff' }} />,
              title: t('landing.feature1Title'),
              desc: t('landing.feature1Desc'),
              img: '/screenshots/ai-analysis.jpg',
            },
            {
              icon: <ThunderboltOutlined style={{ fontSize: 40, color: '#faad14' }} />,
              title: t('landing.feature2Title'),
              desc: t('landing.feature2Desc'),
              img: '/screenshots/alerts.jpg',
            },
            {
              icon: <ApiOutlined style={{ fontSize: 40, color: '#52c41a' }} />,
              title: t('landing.feature3Title'),
              desc: t('landing.feature3Desc'),
              img: '/screenshots/topology.jpg',
            },
          ].map((f, i) => (
            <Col xs={24} md={8} key={i}>
              <Card
                hoverable
                style={{
                  height: '100%',
                  borderRadius: 12,
                  background: isDark ? '#1f1f1f' : '#fafafa',
                  border: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'}`,
                }}
                cover={
                  <Image
                    src={f.img}
                    alt={f.title}
                    preview={false}
                    style={{ height: 200, objectFit: 'cover' }}
                    fallback="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='400' height='200' fill='%23f5f5f5'%3E%3Crect width='400' height='200'/%3E%3C/svg%3E"
                  />
                }
              >
                <div style={{ textAlign: 'center' }}>
                  {f.icon}
                  <Title level={4} style={{ marginTop: 16, color: isDark ? '#fff' : '#000' }}>{f.title}</Title>
                  <Paragraph style={{ color: isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.65)' }}>{f.desc}</Paragraph>
                </div>
              </Card>
            </Col>
          ))}
        </Row>
      </div>

      {/* Stats Section */}
      <div
        style={{
          background: isDark ? '#1a1a2e' : '#f0f5ff',
          padding: '64px 24px',
        }}
      >
        <Row gutter={[32, 32]} justify="center" style={{ maxWidth: 960, margin: '0 auto' }}>
          {[
            { icon: <DashboardOutlined />, value: '<2s', label: t('landing.stat1') },
            { icon: <RobotOutlined />, value: '95%+', label: t('landing.stat2') },
            { icon: <ThunderboltOutlined />, value: '70%', label: t('landing.stat3') },
            { icon: <GlobalOutlined />, value: '24/7', label: t('landing.stat4') },
          ].map((s, i) => (
            <Col xs={12} md={6} key={i} style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 32, color: '#1677ff', marginBottom: 8 }}>{s.icon}</div>
              <Title level={2} style={{ margin: 0, color: isDark ? '#fff' : '#000' }}>{s.value}</Title>
              <Text style={{ color: isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.45)' }}>{s.label}</Text>
            </Col>
          ))}
        </Row>
      </div>

      {/* Comparison Table */}
      <div style={{ maxWidth: 960, margin: '0 auto', padding: '80px 24px' }}>
        <Title level={2} style={{ textAlign: 'center', marginBottom: 16, color: isDark ? '#fff' : '#000' }}>
          {t('landing.comparisonTitle')}
        </Title>
        <Paragraph style={{ textAlign: 'center', marginBottom: 48, fontSize: 16, color: isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.45)' }}>
          {t('landing.comparisonSubtitle')}
        </Paragraph>
        <Table
          columns={comparisonColumns(t)}
          dataSource={comparisonData(t)}
          pagination={false}
          bordered
          size="middle"
        />
      </div>

      {/* CTA Section */}
      <div
        style={{
          textAlign: 'center',
          padding: '80px 24px',
          background: isDark
            ? 'linear-gradient(180deg, #141414 0%, #1a1a2e 100%)'
            : 'linear-gradient(180deg, #ffffff 0%, #f0f5ff 100%)',
        }}
      >
        <Title level={2} style={{ marginBottom: 16, color: isDark ? '#fff' : '#000' }}>
          {t('landing.ctaTitle')}
        </Title>
        <Paragraph style={{ fontSize: 18, marginBottom: 40, color: isDark ? 'rgba(255,255,255,0.65)' : 'rgba(0,0,0,0.45)' }}>
          {t('landing.ctaDescription')}
        </Paragraph>
        <Space size="large">
          <Button type="primary" size="large" icon={<ArrowRightOutlined />} onClick={() => navigate('/login')}>
            {t('landing.getStarted')}
          </Button>
          <Button
            size="large"
            href="https://github.com/lchuangnet/vigilops"
            target="_blank"
            rel="noopener noreferrer"
          >
            {t('landing.viewDocs')}
          </Button>
        </Space>
      </div>

      {/* Footer */}
      <div
        style={{
          textAlign: 'center',
          padding: '32px 24px',
          borderTop: `1px solid ${isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.06)'}`,
          color: isDark ? 'rgba(255,255,255,0.45)' : 'rgba(0,0,0,0.45)',
        }}
      >
        <Text style={{ color: 'inherit' }}>
          &copy; {new Date().getFullYear()} VigilOps. {t('landing.footer')}
        </Text>
      </div>
    </div>
  );
}
