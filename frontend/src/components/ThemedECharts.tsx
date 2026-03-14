/**
 * 主题感知的 ECharts 包装组件
 * 自动应用暗色/亮色主题，透明背景
 */
import ReactECharts, { type EChartsOption } from 'echarts-for-react';
import { useTheme } from '../contexts/ThemeContext';
import { useMemo, type CSSProperties, forwardRef } from 'react';

interface ThemedEChartsProps {
  option: EChartsOption;
  style?: CSSProperties;
  opts?: any;
  notMerge?: boolean;
  lazyUpdate?: boolean;
  onEvents?: Record<string, Function>;
  onChartReady?: (instance: any) => void;
}

const DARK_TEXT = 'rgba(255,255,255,0.65)';
const DARK_SPLIT = 'rgba(255,255,255,0.08)';

const ThemedECharts = forwardRef<any, ThemedEChartsProps>(({ option, ...rest }, ref) => {
  const { isDark } = useTheme();

  const themedOption = useMemo(() => {
    if (!isDark) return option;

    // Deep merge dark overrides into option
    const darkOption = { ...option, backgroundColor: 'transparent' };

    // Title + subtitle
    if (darkOption.title) {
      const t = Array.isArray(darkOption.title) ? darkOption.title : [darkOption.title];
      darkOption.title = t.map((item: any) => ({
        ...item,
        textStyle: { ...item?.textStyle, color: DARK_TEXT },
        subtextStyle: { ...item?.subtextStyle, color: DARK_TEXT },
      }));
      if (!Array.isArray(option.title)) darkOption.title = darkOption.title[0];
    }

    // Legend
    if (darkOption.legend) {
      darkOption.legend = { ...darkOption.legend, textStyle: { ...(darkOption.legend as any)?.textStyle, color: DARK_TEXT } };
    }

    // Axes
    const patchAxis = (axis: any) => {
      if (!axis) return axis;
      const arr = Array.isArray(axis) ? axis : [axis];
      const patched = arr.map((a: any) => ({
        ...a,
        axisLabel: { color: DARK_TEXT, ...a?.axisLabel },
        axisLine: { lineStyle: { color: DARK_SPLIT, ...a?.axisLine?.lineStyle }, ...a?.axisLine },
        splitLine: { lineStyle: { color: DARK_SPLIT, ...a?.splitLine?.lineStyle }, ...a?.splitLine },
      }));
      return Array.isArray(axis) ? patched : patched[0];
    };
    if (darkOption.xAxis) darkOption.xAxis = patchAxis(darkOption.xAxis);
    if (darkOption.yAxis) darkOption.yAxis = patchAxis(darkOption.yAxis);

    return darkOption;
  }, [option, isDark]);

  return (
    <ReactECharts
      ref={ref as any}
      option={themedOption}
      theme={isDark ? 'dark' : undefined}
      {...rest}
    />
  );
});

ThemedECharts.displayName = 'ThemedECharts';
export default ThemedECharts;
