/**
 * 日志统计组件
 * FATAL/ERROR 行红色背景 + AI 分析 CTA，WARN/INFO/DEBUG 正常展示
 */
import { Card, Row, Col, Statistic, Button, Space, Typography } from 'antd';
import { ExclamationCircleFilled } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import ReactECharts from '../ThemedECharts';
import type { LogStats as LogStatsType } from '../../services/logs';

const { Text } = Typography;

interface LogStatsProps {
  logStats: LogStatsType | null;
  onAIAnalyze?: () => void;
}

export default function LogStats({ logStats, onAIAnalyze }: LogStatsProps) {
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
    FATAL: '#722ed1',
  };

  const pieOption = {
    tooltip: { trigger: 'item' as const },
    series: [
      {
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
      },
    ],
  };

  // 按危险程度排序：FATAL > ERROR > WARN > INFO > DEBUG
  const levelOrder = ['FATAL', 'ERROR', 'WARN', 'INFO', 'DEBUG'];
  const sortedLevels = [...logStats.by_level].sort(
    (a, b) => levelOrder.indexOf(a.level) - levelOrder.indexOf(b.level)
  );

  return (
    <Card title={t('dashboard.logStatTitle')}>
      <Row gutter={16} align="middle">
        <Col xs={24} md={10}>
          <Statistic title={t('dashboard.logTotal')} value={totalLogs} />
          <div style={{ marginTop: 12 }}>
            {sortedLevels.map(({ level, count }) => {
              const isFatal = level === 'FATAL';
              const isError = level === 'ERROR';

              if (isFatal || isError) {
                return (
                  <div
                    key={level}
                    style={{
                      background: isFatal ? '#2d0000' : '#1a0000',
                      border: `1px solid ${isFatal ? '#ff4d4f' : '#ff7875'}`,
                      borderLeft: '4px solid #ff4d4f',
                      borderRadius: 6,
                      padding: '6px 12px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      marginBottom: 6,
                    }}
                  >
                    <Space size={6}>
                      <ExclamationCircleFilled style={{ color: '#ff4d4f', fontSize: 14 }} />
                      <Text
                        style={{
                          color: isFatal ? '#ff4d4f' : '#ff7875',
                          fontWeight: 700,
                          fontSize: 13,
                        }}
                      >
                        {level} {count}
                      </Text>
                    </Space>
                    <Button
                      type="primary"
                      danger
                      size="small"
                      onClick={onAIAnalyze}
                    >
                      {t('dashboard.aiAnalyzeLog')}
                    </Button>
                  </div>
                );
              }

              // WARN / INFO / DEBUG 正常展示
              const textColor =
                level === 'WARN' ? '#fa8c16' :
                level === 'INFO' ? '#1677ff' :
                '#8c8c8c';

              return (
                <div
                  key={level}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    padding: '3px 0',
                    marginBottom: 2,
                  }}
                >
                  <Text style={{ fontSize: 13, color: textColor }}>{level}</Text>
                  <Text style={{ fontSize: 13, color: textColor, fontWeight: 500 }}>
                    {count.toLocaleString()}
                  </Text>
                </div>
              );
            })}
          </div>
        </Col>
        <Col xs={24} md={14}>
          <ReactECharts option={pieOption} style={{ height: 200 }} />
        </Col>
      </Row>
    </Card>
  );
}
