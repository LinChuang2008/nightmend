/**
 * PromQL 告警规则编辑器
 *
 * 与既有 metric+threshold 表单并列，用于为 AlertRule 填写 query_expr 与 for_duration_seconds。
 *
 * 交互：
 *   - 600ms debounce 自动校验表达式（/api/v1/promql/query 跑 instant query）
 *   - 手动"立即校验"按钮
 *   - 示例下拉（常用 PromQL 片段），点击直接填入
 *   - 校验成功展示 result type + 首行 series 预览
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert, Button, Dropdown, Form, Input, InputNumber, Space, Spin, Tag, Typography,
} from 'antd';
import { BulbOutlined, ThunderboltOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';

import type { PromQLValidationResult } from '../services/alerts';
import { validatePromQL } from '../services/alerts';

const { Paragraph, Text } = Typography;

export interface PromQLRuleEditorProps {
  /** 当前 query_expr 值；undefined / null 表示未设置 */
  queryExpr?: string | null;
  /** for_duration_seconds */
  forDuration?: number | null;
  /** 值变更回调；编辑器自己不 useState，完全受控 */
  onChange: (patch: { query_expr?: string | null; for_duration_seconds?: number | null }) => void;
  /** 只读模式 —— 内置规则或 sync_at 展示场景 */
  readonly?: boolean;
}

const EXAMPLES: { label: string; expr: string; hint: string }[] = [
  {
    label: '5xx 错误率 > 10%',
    expr: 'rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m]) > 0.1',
    hint: '5 分钟窗口内 5xx 占比超过 10%',
  },
  {
    label: 'CPU 均值 > 80%',
    expr: 'avg by(instance) (100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) by (instance) * 100)) > 80',
    hint: '按 instance 聚合 CPU 使用率',
  },
  {
    label: '内存使用率 > 90%',
    expr: '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100 > 90',
    hint: '可用内存 < 10%',
  },
  {
    label: '磁盘 24h 内将填满',
    expr: 'predict_linear(node_filesystem_avail_bytes{mountpoint="/"}[6h], 24 * 3600) < 0',
    hint: 'predict_linear 按近 6h 趋势外推',
  },
  {
    label: 'target 掉线',
    expr: 'up == 0',
    hint: 'Prometheus 最常见的 target down 告警',
  },
];

export function PromQLRuleEditor({ queryExpr, forDuration, onChange, readonly }: PromQLRuleEditorProps) {
  const { t } = useTranslation();
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<PromQLValidationResult | null>(null);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const runValidation = useCallback(async (expr: string) => {
    if (!expr.trim()) {
      setValidation(null);
      return;
    }
    setValidating(true);
    try {
      const result = await validatePromQL(expr);
      setValidation(result);
    } finally {
      setValidating(false);
    }
  }, []);

  // 表达式变更 → 600ms debounce 后自动校验
  useEffect(() => {
    if (!queryExpr || readonly) {
      setValidation(null);
      return;
    }
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      runValidation(queryExpr);
    }, 600);
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [queryExpr, readonly, runValidation]);

  const applyExample = (expr: string) => {
    if (readonly) return;
    onChange({ query_expr: expr });
  };

  const handleExprChange = (value: string) => {
    if (readonly) return;
    onChange({ query_expr: value.trim() || null });
  };

  const handleForChange = (value: number | null) => {
    if (readonly) return;
    onChange({ for_duration_seconds: value ?? null });
  };

  return (
    <div data-testid="promql-rule-editor">
      <Paragraph type="secondary" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('alerts.promqlEditorHint', '填写 PromQL 表达式后，规则会自动同步到 Prometheus 规则引擎。原有 metric+threshold 字段将被忽略。')}
      </Paragraph>

      <Form.Item
        label={(
          <Space>
            <ThunderboltOutlined />
            <span>PromQL Expression</span>
            {validating && <Spin size="small" />}
            {validation?.valid && <Tag color="success">valid</Tag>}
            {validation && !validation.valid && <Tag color="error">invalid</Tag>}
          </Space>
        )}
        required
      >
        <Input.TextArea
          value={queryExpr ?? ''}
          disabled={readonly}
          onChange={(e) => handleExprChange(e.target.value)}
          placeholder='rate(http_requests_total{status=~"5.."}[5m]) > 0.1'
          autoSize={{ minRows: 3, maxRows: 8 }}
          spellCheck={false}
          style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace', fontSize: 13 }}
        />
      </Form.Item>

      <Space style={{ marginBottom: 12 }} wrap>
        <Dropdown
          disabled={readonly}
          menu={{
            items: EXAMPLES.map((ex, i) => ({
              key: String(i),
              label: (
                <Space direction="vertical" size={0} style={{ maxWidth: 360 }}>
                  <Text strong>{ex.label}</Text>
                  <Text code style={{ fontSize: 11 }}>{ex.expr}</Text>
                  <Text type="secondary" style={{ fontSize: 11 }}>{ex.hint}</Text>
                </Space>
              ),
              onClick: () => applyExample(ex.expr),
            })),
          }}
          trigger={['click']}
        >
          <Button size="small" icon={<BulbOutlined />}>
            {t('alerts.promqlExamples', '示例')}
          </Button>
        </Dropdown>
        <Button
          size="small"
          loading={validating}
          onClick={() => queryExpr && runValidation(queryExpr)}
          disabled={readonly || !queryExpr}
        >
          {t('alerts.promqlValidateNow', '立即校验')}
        </Button>
      </Space>

      {validation && !validation.valid && (
        <Alert
          type="error"
          showIcon
          style={{ marginBottom: 12 }}
          message={validation.message ?? 'Invalid expression'}
        />
      )}
      {validation?.valid && (
        <Alert
          type="success"
          showIcon
          style={{ marginBottom: 12 }}
          message={renderValidationPreview(validation.data)}
        />
      )}

      <Form.Item
        label={t('alerts.promqlFor', '持续时长 for (秒)')}
        tooltip={t('alerts.promqlForTip', '表达式持续满足这么久才触发告警，对应 Prometheus rule.for')}
      >
        <InputNumber
          min={0}
          step={30}
          value={forDuration ?? undefined}
          disabled={readonly}
          onChange={handleForChange}
          placeholder="默认取 duration_seconds，至少 60"
          style={{ width: 240 }}
          addonAfter="s"
        />
      </Form.Item>
    </div>
  );
}

/** 根据 PromQL 返回值渲染简短 preview */
function renderValidationPreview(data: unknown): string {
  if (!data || typeof data !== 'object') return '表达式合法';
  const d = data as { resultType?: string; result?: unknown[] };
  const resultType = d.resultType ?? 'unknown';
  const count = Array.isArray(d.result) ? d.result.length : 0;
  return `合法 · resultType=${resultType}, series=${count}`;
}

export default PromQLRuleEditor;
