/**
 * 核心指标卡片组件
 * 显示服务器、服务、数据库统计；第5列为异常日志 KPI（健康评分圆环已移至 ZONE A）
 * 支持可选 delta 趋势指示
 */
import { Row, Col, Card, Statistic, Tag, Button, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import {
  CloudServerOutlined, ApiOutlined, AlertOutlined,
  CheckCircleOutlined, CloseCircleOutlined, DatabaseOutlined,
  WarningOutlined, ArrowUpOutlined, ArrowDownOutlined, MinusOutlined,
} from '@ant-design/icons';
import type { DatabaseItem } from '../../services/databases';

interface MetricsCardsProps {
  hostTotal: number;
  hostOnline: number;
  hostOffline: number;
  svcTotal: number;
  svcHealthy: number;
  svcUnhealthy: number;
  alertFiring: number;
  dbItems: DatabaseItem[];
  fatalCount: number;
  errorCount: number;
  onAIAnalyze: () => void;
  prevHostOnline?: number;
  prevSvcHealthy?: number;
  prevAlertFiring?: number;
  prevAbnormalCount?: number;
}

function TrendDelta({ current, previous, invertColor }: { current: number; previous?: number; invertColor?: boolean }) {
  const { token } = theme.useToken();
  if (previous === undefined) return null;
  const delta = current - previous;
  if (delta === 0) {
    return (
      <span style={{ fontSize: 12, color: token.colorTextTertiary, marginLeft: 6 }}>
        <MinusOutlined /> 0
      </span>
    );
  }
  const isUp = delta > 0;
  const color = invertColor
    ? (isUp ? token.colorError : token.colorSuccess)
    : (isUp ? token.colorSuccess : token.colorError);
  return (
    <span style={{ fontSize: 12, color, marginLeft: 6, fontWeight: 500 }}>
      {isUp ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
      {' '}{isUp ? `+${delta}` : delta}
    </span>
  );
}

export default function MetricsCards({
  hostTotal, hostOnline, hostOffline,
  svcTotal, svcHealthy, svcUnhealthy,
  alertFiring, dbItems,
  fatalCount, errorCount, onAIAnalyze,
  prevHostOnline, prevSvcHealthy, prevAlertFiring, prevAbnormalCount,
}: MetricsCardsProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const abnormalCount = fatalCount + errorCount;

  return (
    <Row gutter={[16, 16]}>
      <Col xs={12} sm={12} md={8} xxl={5}>
        <Card>
          <Statistic title={t('dashboard.servers')} value={hostTotal} prefix={<CloudServerOutlined />} />
          <div style={{ marginTop: 8 }}>
            <Tag icon={<CheckCircleOutlined />} color="success">{t('dashboard.online')} {hostOnline}</Tag>
            <TrendDelta current={hostOnline} previous={prevHostOnline} />
            <Tag icon={<CloseCircleOutlined />} color="error">{t('dashboard.offline')} {hostOffline}</Tag>
          </div>
        </Card>
      </Col>
      <Col xs={12} sm={12} md={8} xxl={5}>
        <Card>
          <Statistic title={t('dashboard.services')} value={svcTotal} prefix={<ApiOutlined />} />
          <div style={{ marginTop: 8 }}>
            <Tag color="success">{t('dashboard.healthy')} {svcHealthy}</Tag>
            <TrendDelta current={svcHealthy} previous={prevSvcHealthy} />
            <Tag color="error">{t('dashboard.unhealthy')} {svcUnhealthy}</Tag>
          </div>
        </Card>
      </Col>
      <Col xs={12} sm={12} md={8} xxl={5}>
        <Card>
          <Statistic title={t('dashboard.databases')} value={dbItems.length} prefix={<DatabaseOutlined />} />
          <div style={{ marginTop: 8 }}>
            <Tag color="success">{t('dashboard.healthy')} {dbItems.filter(x => x.status === 'healthy').length}</Tag>
            <Tag color="error">{t('dashboard.unhealthy')} {dbItems.filter(x => x.status !== 'healthy' && x.status !== 'unknown').length}</Tag>
          </div>
        </Card>
      </Col>
      <Col xs={12} sm={12} md={12} xxl={5}>
        <Card>
          <Statistic
            title={t('dashboard.activeAlerts')}
            value={alertFiring}
            prefix={<AlertOutlined />}
            valueStyle={{ color: alertFiring > 0 ? token.colorError : token.colorSuccess }}
          />
          <TrendDelta current={alertFiring} previous={prevAlertFiring} invertColor />
        </Card>
      </Col>
      {/* 第5列：异常日志 KPI（替换原健康评分圆环） */}
      <Col xs={24} sm={12} md={12} xxl={4}>
        <Card
          style={{
            borderTop: abnormalCount > 0 ? `3px solid ${token.colorError}` : `3px solid ${token.colorBorderSecondary}`,
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <Statistic
              title={t('dashboard.abnormalLogs')}
              value={abnormalCount}
              prefix={<WarningOutlined />}
              valueStyle={{ color: abnormalCount > 0 ? token.colorError : token.colorSuccess }}
            />
            {abnormalCount > 0 && (
              <Button type="primary" danger size="small" onClick={onAIAnalyze}>
                {t('dashboard.aiAnalyzeLog')}
              </Button>
            )}
          </div>
          <div style={{ marginTop: 8 }}>
            {fatalCount > 0 && <Tag color="purple">FATAL {fatalCount}</Tag>}
            {errorCount > 0 && <Tag color="red">ERROR {errorCount}</Tag>}
            <TrendDelta current={abnormalCount} previous={prevAbnormalCount} invertColor />
          </div>
        </Card>
      </Col>
    </Row>
  );
}
