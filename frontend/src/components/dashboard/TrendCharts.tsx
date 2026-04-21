/**
 * 24小时趋势图组件
 * 带图表标题、副标题及阈值 markLine
 */
import { memo } from 'react';
import { Row, Col, Card } from 'antd';
import { useTranslation } from 'react-i18next';
import ReactECharts from '../ThemedECharts';

interface TrendPoint {
  hour: string;
  avg_cpu: number | null;
  avg_mem: number | null;
  alert_count: number;
  error_log_count: number;
}

interface TrendChartsProps {
  trends: TrendPoint[];
}

export default memo(function TrendCharts({ trends }: TrendChartsProps) {
  const { t } = useTranslation();

  if (trends.length === 0) {
    return null;
  }

  const makeOption = (
    values: (number | null)[],
    color: string,
    titleText: string,
    opts?: {
      thresholdY?: number;
      thresholdLabel?: string;
      showAvgLine?: boolean;
    }
  ) => {
    const markLineData: any[] = [];

    if (opts?.thresholdY != null) {
      markLineData.push({
        yAxis: opts.thresholdY,
        lineStyle: { color: '#faad14', type: 'dashed', width: 1.5 },
        label: {
          formatter: opts.thresholdLabel ?? `${opts.thresholdY}%`,
          position: 'insideEndTop',
          color: '#faad14',
          fontSize: 10,
        },
      });
    }

    if (opts?.showAvgLine) {
      markLineData.push({
        type: 'average',
        name: t('dashboard.avgLabel'),
        lineStyle: { color: '#10B981', type: 'dotted', width: 1.5 },
        label: {
          formatter: t('dashboard.avgLabel'),
          position: 'insideEndTop',
          color: '#10B981',
          fontSize: 10,
        },
      });
    }

    return {
      title: {
        text: titleText,
        subtext: t('dashboard.last24h'),
        left: 'left',
        top: 0,
        textStyle: { fontSize: 13, fontWeight: 600, color: '#333' },
        subtextStyle: { fontSize: 11, color: '#999' },
      },
      tooltip: {
        trigger: 'axis' as const,
        formatter: (params: any) =>
          params[0]?.value != null ? `${params[0].value}` : t('dashboard.noData'),
      },
      xAxis: {
        type: 'category' as const,
        show: false,
        data: values.map((_, i) => i),
      },
      yAxis: {
        type: 'value' as const,
        show: false,
      },
      series: [
        {
          type: 'line' as const,
          data: values,
          smooth: true,
          symbol: 'none',
          lineStyle: { color, width: 2 },
          areaStyle: { color: `${color}33` },
          ...(markLineData.length > 0
            ? {
                markLine: {
                  silent: true,
                  symbol: 'none',
                  data: markLineData,
                },
              }
            : {}),
        },
      ],
      grid: { top: 52, bottom: 10, left: 10, right: 10 },
    };
  };

  const cpuTrend = trends.map(tp => tp.avg_cpu);
  const memTrend = trends.map(tp => tp.avg_mem);
  const alertTrend = trends.map(tp => tp.alert_count);
  const errorTrend = trends.map(tp => tp.error_log_count);

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} md={6}>
        <Card styles={{ body: { padding: '12px' } }}>
          <ReactECharts
            option={makeOption(cpuTrend, '#10B981', t('dashboard.cpuTrendFull'), {
              thresholdY: 80,
              thresholdLabel: t('dashboard.thresholdLabel'),
            })}
            style={{ height: 200 }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card styles={{ body: { padding: '12px' } }}>
          <ReactECharts
            option={makeOption(memTrend, '#52c41a', t('dashboard.memTrendFull'), {
              thresholdY: 80,
              thresholdLabel: t('dashboard.thresholdLabel'),
            })}
            style={{ height: 200 }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card styles={{ body: { padding: '12px' } }}>
          <ReactECharts
            option={makeOption(alertTrend, '#fa8c16', t('dashboard.alertTrendFull'))}
            style={{ height: 200 }}
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card styles={{ body: { padding: '12px' } }}>
          <ReactECharts
            option={makeOption(errorTrend, '#ff4d4f', t('dashboard.errorLogTrendFull'), {
              showAvgLine: true,
            })}
            style={{ height: 200 }}
          />
        </Card>
      </Col>
    </Row>
  );
})
