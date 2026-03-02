/**
 * 日志统计组件
 */
import { Card, Row, Col, Statistic, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import ReactECharts from '../ThemedECharts';
import type { LogStats as LogStatsType } from '../../services/logs';

const { Text } = Typography;

interface LogStatsProps {
  logStats: LogStatsType | null;
}

export default function LogStats({ logStats }: LogStatsProps) {
  const { t } = useTranslation();

  if (!logStats || logStats.by_level.length === 0) {
    return (
      <Card title={t('dashboard.logStatTitle')}>
        <Text type="secondary">{t('dashboard.noData')}</Text>
      </Card>
    );
  }

  const totalLogs = logStats.by_level.reduce((sum, level) => sum + level.count, 0);
  
  const levelColors: Record<string, string> = {
    DEBUG: '#bfbfbf',
    INFO: '#1677ff', 
    WARN: '#faad14',
    ERROR: '#ff4d4f',
    FATAL: '#722ed1'
  };

  const levelTagColors: Record<string, string> = {
    DEBUG: 'default',
    INFO: 'blue',
    WARN: 'orange', 
    ERROR: 'red',
    FATAL: 'purple'
  };

  const pieOption = {
    tooltip: { trigger: 'item' as const },
    series: [{
      type: 'pie' as const,
      radius: ['40%', '70%'],
      data: logStats.by_level
        .filter(l => l.count > 0)
        .map(({ level, count }) => ({
          name: level,
          value: count,
          itemStyle: { color: levelColors[level] || '#999' },
        })),
      label: { formatter: '{b}: {c}' },
    }],
  };

  return (
    <Card title={t('dashboard.logStatTitle')}>
      <Row gutter={16} align="middle">
        <Col xs={24} md={8}>
          <Statistic title={t('dashboard.logTotal')} value={totalLogs} />
          <div style={{ marginTop: 8 }}>
            {logStats.by_level.map(({ level, count }) => (
              <Tag 
                key={level} 
                color={levelTagColors[level] || 'default'}
                style={{ marginBottom: 4 }}
              >
                {level}: {count}
              </Tag>
            ))}
          </div>
        </Col>
        <Col xs={24} md={16}>
          <ReactECharts 
            option={pieOption}
            style={{ height: 200 }} 
          />
        </Col>
      </Row>
    </Card>
  );
}
