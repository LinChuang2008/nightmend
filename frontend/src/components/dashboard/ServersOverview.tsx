/**
 * 服务器健康总览条组件
 * 三色进度条（绿/黄/红），四状态卡片边框
 */
import { Card, Row, Col, Space, Progress, Tooltip, Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import { DesktopOutlined, ArrowRightOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';

const { Text } = Typography;

interface HostItem {
  id: string;
  hostname: string;
  display_name?: string | null;
  ip_address?: string | null;
  private_ip?: string | null;
  public_ip?: string | null;
  network_info?: {
    private_ip?: string;
    public_ip?: string;
    all_private?: string[];
    all_public?: string[];
    interfaces?: Record<string, { ipv4: string; type: string }>;
  } | null;
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

/**
 * 三色语义进度条颜色
 * <60%: 绿色安全，60-threshold: 黄色警告，>threshold: 红色危险
 */
function getMetricColor(percent: number, dangerThreshold = 80): string {
  if (percent < 60) return '#52c41a';
  if (percent < dangerThreshold) return '#faad14';
  return '#ff4d4f';
}

export default function ServersOverview({ hosts }: ServersOverviewProps) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const { token } = theme.useToken();

  if (hosts.length === 0) {
    return null;
  }

  // 获取主机显示名称（优先使用 display_name）
  const getDisplayName = (host: HostItem): string => {
    return host.display_name || host.hostname;
  };

  // 获取主机显示 IP（优先内网 IP，否则公网 IP，最后兼容旧字段）
  const getDisplayIp = (host: HostItem): string => {
    return host.private_ip || host.ip_address || host.public_ip || 'N/A';
  };

  // 判断是否有多个 IP 需要显示提示
  const hasMultipleIps = (host: HostItem): boolean => {
    return !!(host.private_ip && host.public_ip);
  };

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
          const displayName = getDisplayName(host);
          const displayIp = getDisplayIp(host);

          const hasDanger =
            (m?.cpu_percent ?? 0) > 80 ||
            (m?.memory_percent ?? 0) > 80 ||
            (m?.disk_percent ?? 0) > 85;

          const hasWarning =
            !hasDanger &&
            ((m?.cpu_percent ?? 0) > 60 ||
              (m?.memory_percent ?? 0) > 60 ||
              (m?.disk_percent ?? 0) > 60);

          const borderColor = !isOnline
            ? token.colorError
            : hasDanger
            ? token.colorError
            : hasWarning
            ? token.colorWarning
            : token.colorSuccess;

          return (
            <Col key={host.id} xs={24} sm={12} md={8} lg={6}>
              <Card
                size="small"
                hoverable
                onClick={() => navigate(`/hosts/${host.id}`)}
                style={{
                  borderLeft: `3px solid ${borderColor}`,
                  cursor: 'pointer',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: 8,
                  }}
                >
                  <Space size={4}>
                    <span
                      style={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        display: 'inline-block',
                        backgroundColor: isOnline ? token.colorSuccess : token.colorError,
                      }}
                    />
                    <Text strong style={{ fontSize: 13 }}>
                      {displayName}
                    </Text>
                  </Space>
                  <ArrowRightOutlined style={{ color: token.colorTextTertiary, fontSize: 11 }} />
                </div>

                {/* IP 地址显示 */}
                <div style={{ marginBottom: 6 }}>
                  {hasMultipleIps(host) ? (
                    <Tooltip title={
                      <div>
                        <div>公网: {host.public_ip}</div>
                        <div>内网: {host.private_ip}</div>
                      </div>
                    }>
                      <Text type="secondary" style={{ fontSize: 11 }}>
                        {displayIp}
                        <Text type="secondary"> (+1)</Text>
                      </Text>
                    </Tooltip>
                  ) : (
                    <Text type="secondary" style={{ fontSize: 11 }}>
                      {displayIp}
                    </Text>
                  )}
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
                          strokeColor={getMetricColor(m.cpu_percent)}
                        />
                        <Text
                          style={{
                            fontSize: 11,
                            color: getMetricColor(m.cpu_percent),
                          }}
                        >
                          {m.cpu_percent}%
                        </Text>
                      </div>
                    </Tooltip>
                    <Tooltip title={`${t('common.memory', { defaultValue: 'Mem' })}: ${m.memory_percent}%`}>
                      <div style={{ flex: 1 }}>
                        <Text type="secondary" style={{ fontSize: 11 }}>
                          {t('common.memory', { defaultValue: 'Mem' })}
                        </Text>
                        <Progress
                          percent={m.memory_percent}
                          size="small"
                          showInfo={false}
                          strokeColor={getMetricColor(m.memory_percent)}
                        />
                        <Text
                          style={{
                            fontSize: 11,
                            color: getMetricColor(m.memory_percent),
                          }}
                        >
                          {m.memory_percent}%
                        </Text>
                      </div>
                    </Tooltip>
                    {m.disk_percent != null && (
                      <Tooltip title={`Disk: ${m.disk_percent}%`}>
                        <div style={{ flex: 1 }}>
                          <Text type="secondary" style={{ fontSize: 11 }}>
                            {t('common.disk', { defaultValue: 'Disk' })}
                          </Text>
                          <Progress
                            percent={m.disk_percent}
                            size="small"
                            showInfo={false}
                            strokeColor={getMetricColor(m.disk_percent, 85)}
                          />
                          <Text
                            style={{
                              fontSize: 11,
                              color: getMetricColor(m.disk_percent, 85),
                            }}
                          >
                            {m.disk_percent}%
                          </Text>
                        </div>
                      </Tooltip>
                    )}
                  </div>
                ) : (
                  <Text type="secondary" style={{ fontSize: 12 }}>
                    {t('dashboard.noMetrics')}
                  </Text>
                )}
              </Card>
            </Col>
          );
        })}
      </Row>
    </Card>
  );
}
