/**
 * 服务器健康总览条组件
 */
import { Card, Row, Col, Space, Progress, Tooltip, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { DesktopOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Text } = Typography;

interface HostItem {
  id: string;
  hostname: string;
  ip_address?: string;
  status: string;
  cpu_cores?: number;
  memory_total_mb?: number;
  latest_metrics?: {
    cpu_percent: number;
    memory_percent: number;
    disk_percent?: number;
    disk_used_mb?: number;
    disk_total_mb?: number;
    net_send_rate_kb?: number;
    net_recv_rate_kb?: number;
    net_packet_loss_rate?: number;
  };
}

interface ServersOverviewProps {
  hosts: HostItem[];
}

export default function ServersOverview({ hosts }: ServersOverviewProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();

  if (hosts.length === 0) {
    return null;
  }

  return (
    <Card
      title={<Space><DesktopOutlined /> {t('dashboard.serverHealthOverview')}</Space>}
      size="small"
      styles={{ body: { padding: '12px 16px' } }}
    >
      <Row gutter={[12, 12]}>
        {hosts.map(host => {
          const m = host.latest_metrics;
          const isOnline = host.status === 'online';
          const cpuHigh = (m?.cpu_percent ?? 0) > 80;
          const memHigh = (m?.memory_percent ?? 0) > 80;
          const diskHigh = (m?.disk_percent ?? 0) > 85;
          const hasWarning = cpuHigh || memHigh || diskHigh;

          return (
            <Col key={host.id} xs={24} sm={12} md={8} lg={6}>
              <Card
                size="small"
                hoverable
                onClick={() => navigate(`/hosts/${host.id}`)}
                style={{
                  borderLeft: `3px solid ${!isOnline ? '#ff4d4f' : hasWarning ? '#faad14' : '#52c41a'}`,
                  cursor: 'pointer',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                  <Space size={4}>
                    <span style={{
                      width: 8, height: 8, borderRadius: '50%', display: 'inline-block',
                      backgroundColor: isOnline ? '#52c41a' : '#ff4d4f',
                    }} />
                    <Text strong style={{ fontSize: 13 }}>{host.hostname}</Text>
                  </Space>
                  <ArrowRightOutlined style={{ color: '#999', fontSize: 11 }} />
                </div>
                {m ? (
                  <div style={{ display: 'flex', gap: 12 }}>
                    <Tooltip title={`CPU: ${m.cpu_percent}%`}>
                      <div style={{ flex: 1 }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>CPU</Text>
                        <Progress
                          percent={m.cpu_percent}
                          size="small"
                          showInfo={false}
                          strokeColor={cpuHigh ? '#ff4d4f' : '#1677ff'}
                        />
                        <Text style={{ fontSize: 11, color: cpuHigh ? '#ff4d4f' : undefined }}>{m.cpu_percent}%</Text>
                      </div>
                    </Tooltip>
                    <Tooltip title={`${t('dashboard.memTrend').split(' ')[0]}: ${m.memory_percent}%`}>
                      <div style={{ flex: 1 }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>{t('common.memory', { defaultValue: 'Mem' })}</Text>
                        <Progress
                          percent={m.memory_percent}
                          size="small"
                          showInfo={false}
                          strokeColor={memHigh ? '#ff4d4f' : '#52c41a'}
                        />
                        <Text style={{ fontSize: 11, color: memHigh ? '#ff4d4f' : undefined }}>{m.memory_percent}%</Text>
                      </div>
                    </Tooltip>
                    {m.disk_percent != null && (
                      <Tooltip title={`Disk: ${m.disk_percent}%`}>
                        <div style={{ flex: 1 }}>
                          <Text type="secondary" style={{ fontSize: 11 }}>{t('common.disk', { defaultValue: 'Disk' })}</Text>
                          <Progress
                            percent={m.disk_percent}
                            size="small"
                            showInfo={false}
                            strokeColor={diskHigh ? '#ff4d4f' : '#faad14'}
                          />
                          <Text style={{ fontSize: 11, color: diskHigh ? '#ff4d4f' : undefined }}>{m.disk_percent}%</Text>
                        </div>
                      </Tooltip>
                    )}
                  </div>
                ) : (
                  <Text type="secondary" style={{ fontSize: 12 }}>{t('dashboard.noMetrics')}</Text>
                )}
              </Card>
            </Col>
          );
        })}
      </Row>
    </Card>
  );
}
