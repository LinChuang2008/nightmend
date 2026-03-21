/**
 * 屏蔽规则服务 (Suppression Rules Service)
 *
 * 提供屏蔽规则的 CRUD 接口和快速屏蔽功能。
 */

import api from './api';

// 屏蔽规则类型定义
export interface SuppressionRule {
  id: number;
  resource_type: string;
  resource_id?: number | null;
  resource_pattern?: string | null;
  alert_rule_id?: number | null;
  start_time?: string | null;
  end_time?: string | null;
  suppress_alerts: boolean;
  suppress_notifications: boolean;
  suppress_ai_analysis: boolean;
  suppress_log_scan: boolean;
  reason?: string | null;
  created_by?: string | null;
  is_active: boolean;
  match_count: number;
  created_at: string;
  updated_at: string;
}

// 创建屏蔽规则请求
export interface SuppressionRuleCreate {
  resource_type: string;
  resource_id?: number | null;
  resource_pattern?: string | null;
  alert_rule_id?: number | null;
  start_time?: string | null;
  end_time?: string | null;
  suppress_alerts?: boolean;
  suppress_notifications?: boolean;
  suppress_ai_analysis?: boolean;
  suppress_log_scan?: boolean;
  reason?: string | null;
}

// 快速屏蔽请求
export interface QuickSuppressRequest {
  resource_type: 'host' | 'service';
  resource_id: number;
  reason?: string | null;
  duration_hours?: number | null;
}

// 屏蔽规则列表响应
export interface SuppressionRuleListResponse {
  items: SuppressionRule[];
  total: number;
  page: number;
  page_size: number;
}

// 屏蔽规则服务
export const suppressionRuleService = {
  /**
   * 获取屏蔽规则列表
   */
  list: (params: {
    resource_type?: string;
    page?: number;
    page_size?: number;
  } = {}) =>
    api.get<SuppressionRuleListResponse>('/suppression-rules', { params }),

  /**
   * 获取单个屏蔽规则
   */
  get: (id: number) =>
    api.get<SuppressionRule>(`/suppression-rules/${id}`),

  /**
   * 创建屏蔽规则
   */
  create: (data: SuppressionRuleCreate) =>
    api.post<SuppressionRule>('/suppression-rules', data),

  /**
   * 快速屏蔽（用于前端"忽略"按钮）
   */
  quickSuppress: (data: QuickSuppressRequest) =>
    api.post<SuppressionRule>('/suppression-rules/quick-suppress', data),

  /**
   * 更新屏蔽规则
   */
  update: (id: number, data: Partial<SuppressionRuleCreate>) =>
    api.put<SuppressionRule>(`/suppression-rules/${id}`, data),

  /**
   * 删除屏蔽规则（软删除）
   */
  delete: (id: number) =>
    api.delete(`/suppression-rules/${id}`),

  /**
   * 检查屏蔽状态
   */
  check: (params: {
    resource_type: string;
    resource_id?: number;
    alert_rule_id?: number;
  }) =>
    api.get<{ suppressed: boolean; rules: Array<{ id: number; reason?: string; end_time?: string | null }> }>(
      '/suppression-rules/check',
      { params }
    ),
};
