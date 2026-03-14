/**
 * 健康评分仪表盘组件
 * 大号 ECharts gauge，三段渐变弧（0-60绿/60-80黄/80-100红），下方 Top3 扣分项
 */
import { memo } from 'react';
import { Typography, theme } from 'antd';
import { useTranslation } from 'react-i18next';
import ReactECharts from '../ThemedECharts';

const { Text } = Typography;

export interface ScoreDeduction {
  reason: string;
  points: number;
}

interface HealthScoreGaugeProps {
  score: number;
  breakdown: ScoreDeduction[];
}

function getScoreColor(s: number): string {
  if (s < 60) return '#52c41a';
  if (s < 80) return '#faad14';
  return '#ff4d4f';
}

export default memo(function HealthScoreGauge({ score, breakdown }: HealthScoreGaugeProps) {
  const { t } = useTranslation();
  const { token } = theme.useToken();
  const scoreColor = getScoreColor(score);

  const statusText =
    score < 60
      ? t('dashboard.scoreHealthy')
      : score < 80
      ? t('dashboard.scoreWarning')
      : t('dashboard.scoreDanger');

  const gaugeOption = {
    series: [
      {
        type: 'gauge' as const,
        startAngle: 210,
        endAngle: -30,
        min: 0,
        max: 100,
        radius: '90%',
        pointer: { show: false },
        progress: {
          show: true,
          width: 16,
          itemStyle: {
            color: {
              type: 'linear' as const,
              x: 0,
              y: 0,
              x2: 1,
              y2: 0,
              colorStops: [
                { offset: 0,   color: '#52c41a' },
                { offset: 0.6, color: '#52c41a' },
                { offset: 0.6, color: '#faad14' },
                { offset: 0.8, color: '#faad14' },
                { offset: 0.8, color: '#ff4d4f' },
                { offset: 1,   color: '#ff4d4f' },
              ],
            },
          },
        },
        axisLine: {
          lineStyle: {
            width: 16,
            color: [[1, token.colorBorderSecondary]] as [number, string][],
          },
        },
        axisTick: { show: false },
        splitLine: { show: false },
        axisLabel: { show: false },
        detail: {
          valueAnimation: true,
          formatter: '{value}',
          fontSize: 36,
          fontWeight: 800 as const,
          offsetCenter: [0, '10%'],
          color: scoreColor,
        },
        data: [{ value: score }],
      },
    ],
  };

  const top3 = breakdown.slice(0, 3);

  return (
    <div
      style={{
        background: token.colorBgContainer,
        borderRadius: 12,
        padding: '12px 16px',
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        boxShadow: token.boxShadowTertiary,
      }}
    >
      <Text strong style={{ fontSize: 13 }}>
        {t('dashboard.healthScore')}
      </Text>
      <ReactECharts option={gaugeOption} style={{ height: 150, marginTop: 4 }} />
      <div style={{ textAlign: 'center', marginTop: -12, marginBottom: 8 }}>
        <Text style={{ fontSize: 12, color: scoreColor, fontWeight: 600 }}>
          {statusText}
        </Text>
      </div>
      {top3.length > 0 && (
        <div>
          {top3.map((d, i) => (
            <div
              key={i}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                marginBottom: 2,
              }}
            >
              <Text style={{ fontSize: 11, color: token.colorTextSecondary }}>▸ {d.reason}</Text>
              <Text style={{ fontSize: 11, color: '#ff4d4f', fontWeight: 600 }}>
                {d.points}pt
              </Text>
            </div>
          ))}
        </div>
      )}
    </div>
  );
})
