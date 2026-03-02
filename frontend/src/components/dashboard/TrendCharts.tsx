/**
 * 24小时趋势图组件
 * 显示 CPU、内存、告警、错误日志的24小时趋势
 */
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

export default function TrendCharts({ trends }: TrendChartsProps) {
  const { t } = useTranslation();

  if (trends.length === 0) {
    return null;
  }

  const sparklineOption = (values: (number | null)[], color: string, title: string) => ({
    title: { 
      text: title, 
      left: 'center', 
      top: 0, 
      textStyle: { fontSize: 12, color: '#666' } 
    },
    tooltip: { 
      trigger: 'axis' as const, 
      formatter: (params: any) => params[0]?.value != null ? `${params[0].value}` : t('dashboard.noData')
    },
    xAxis: { 
      type: 'category' as const, 
      show: false, 
      data: values.map((_, i) => i) 
    },
    yAxis: { 
      type: 'value' as const, 
      show: false 
    },
    series: [{
      type: 'line' as const,
      data: values,
      smooth: true,
      symbol: 'none',
      lineStyle: { color, width: 2 },
      areaStyle: { color: `${color}33` }
    }],
    grid: { top: 30, bottom: 10, left: 10, right: 10 },
  });

  const cpuTrend = trends.map(tp => tp.avg_cpu);
  const memTrend = trends.map(tp => tp.avg_mem);
  const alertTrend = trends.map(tp => tp.alert_count);
  const errorTrend = trends.map(tp => tp.error_log_count);

  return (
    <Row gutter={[16, 16]}>
      <Col xs={24} sm={12} md={6}>
        <Card styles={{ body: { padding: '12px' } }}>
          <ReactECharts 
            option={sparklineOption(cpuTrend, '#1677ff', t('dashboard.cpuTrend'))} 
            style={{ height: 200 }} 
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card styles={{ body: { padding: '12px' } }}>
          <ReactECharts 
            option={sparklineOption(memTrend, '#52c41a', t('dashboard.memTrend'))} 
            style={{ height: 200 }} 
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card styles={{ body: { padding: '12px' } }}>
          <ReactECharts 
            option={sparklineOption(alertTrend, '#faad14', t('dashboard.alertTrend'))} 
            style={{ height: 200 }} 
          />
        </Card>
      </Col>
      <Col xs={24} sm={12} md={6}>
        <Card styles={{ body: { padding: '12px' } }}>
          <ReactECharts 
            option={sparklineOption(errorTrend, '#ff4d4f', t('dashboard.errorLogTrend'))} 
            style={{ height: 200 }} 
          />
        </Card>
      </Col>
    </Row>
  );
}
