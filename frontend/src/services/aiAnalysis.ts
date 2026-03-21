/**
 * AI 分析服务：洞察查询、告警根因分析、日志分析
 */
import api from './api';

export interface AIInsightItem {
  id: number;
  insight_type: string;
  severity: string;
  title: string;
  summary: string;
  details?: Record<string, unknown> | null;
  related_host_id?: number | null;
  related_alert_id?: number | null;
  status: string;
  created_at: string;
  conclusion?: string;
}

export interface RootCauseResult {
  root_cause: string;
  impact: string;
  suggestions: string[];
  severity: string;
}

export interface LogAnalysisResult {
  summary: string;
  title: string;
  severity: string;
  log_count: number;
  patterns: string[];
  suggestions: string[];
  details?: Record<string, unknown> | null;
}

export const aiAnalysisApi = {
  listInsights: (params?: { limit?: number; offset?: number; severity?: string; status?: string }) =>
    api.get<{ total: number; items: AIInsightItem[] }>('/ai/insights', { params }),

  getInsight: (id: number) => api.get<AIInsightItem>(`/ai/insights/${id}`),

  rootCause: (alertId: number | string) =>
    api.post<RootCauseResult>(`/ai/root-cause?alert_id=${alertId}`),

  analyze: (alertId: number | string) =>
    api.get<{ summary: string; analysis: unknown; root_cause?: string; cached: boolean }>(
      '/ai/analyze',
      { params: { alert_id: alertId } },
    ),

  analyzeLogs: (hours = 1) =>
    api.post<LogAnalysisResult>(`/ai/analyze-logs?hours=${hours}`),
};
