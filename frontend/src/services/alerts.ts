/**
 * 告警服务模块
 * 提供告警事件、告警规则和通知渠道的 API 调用方法
 */
import api from './api';

/** 告警事件 */
export interface Alert {
  /** 告警唯一标识 */
  id: string;
  /** 关联主机 ID */
  host_id: string | null;
  /** 关联服务 ID */
  service_id: string | null;
  /** 触发的规则 ID */
  rule_id: string;
  /** 严重程度（info / warning / critical） */
  severity: string;
  /** 告警状态（firing / resolved / acknowledged） */
  status: string;
  /** 告警标题 */
  title: string;
  /** 英文告警标题 */
  title_en?: string | null;
  /** 告警详细信息 */
  message: string;
  /** 触发时间 */
  fired_at: string;
  /** 恢复时间 */
  resolved_at: string | null;
  /** 确认时间 */
  acknowledged_at: string | null;
  /** 确认人 */
  acknowledged_by: string | null;
}

/** 告警规则 */
export interface AlertRule {
  id: string;
  /** 规则名称 */
  name: string;
  /** 监控指标名 */
  metric: string;
  /** 比较运算符（> / < / == 等） */
  operator: string;
  /** 阈值 */
  threshold: number;
  /** 持续时间（秒），超过后才触发告警 */
  duration_seconds: number;
  /** 严重程度 */
  severity: string;
  /** 是否启用 */
  enabled: boolean;
  /** 是否为内置规则 */
  is_builtin: boolean;
  /** 是否已启用（与 enabled 配合使用） */
  is_enabled: boolean;
  created_at: string;
  /** 规则类型（metric / log / database） */
  rule_type?: string;
  /** 日志关键词匹配 */
  log_keyword?: string;
  /** 日志级别过滤 */
  log_level?: string;
  /** 日志服务名过滤 */
  log_service?: string;
  /** 数据库指标名 */
  db_metric_name?: string;
  /** 关联数据库 ID */
  db_id?: number;
  /** 冷却时间（秒），避免重复告警 */
  cooldown_seconds?: number;
  /** 持续告警模式：开启后将在持续违规期间按冷却期重复发送通知，关闭则仅在恢复时发送 */
  continuous_alert?: boolean;
  /** 静默开始时间 */
  silence_start?: string | null;
  /** 静默结束时间 */
  silence_end?: string | null;
  /** 关联的通知渠道 ID 列表 */
  notification_channel_ids?: number[] | null;
  /** PromQL 表达式；非空时走 Prometheus sidecar 触发路径，否则走内置 metric+threshold */
  query_expr?: string | null;
  /** PromQL 规则的 for 字段（秒），即表达式持续满足的时长 */
  for_duration_seconds?: number | null;
  /** 上次同步到 Prometheus rules.yml 的 ISO 时间戳（只读）*/
  prom_rule_synced_at?: string | null;
}

/** 通知渠道 */
export interface NotificationChannel {
  id: number;
  /** 渠道名称 */
  name: string;
  /** 渠道类型（email / webhook / dingtalk 等） */
  type: string;
  /** 渠道配置（JSON 格式，不同类型结构不同） */
  config: Record<string, unknown>;
  /** 是否启用 */
  is_enabled: boolean;
  created_at: string;
}

/** 通知发送记录 */
export interface NotificationLog {
  id: number;
  /** 关联告警 ID */
  alert_id: number;
  /** 关联通知渠道 ID */
  channel_id: number;
  /** 发送状态（success / failed） */
  status: string;
  /** HTTP 响应码 */
  response_code?: number;
  /** 错误信息 */
  error?: string;
  /** 重试次数 */
  retries: number;
  /** 发送时间 */
  sent_at: string;
  /** 关联渠道名称（接口补充） */
  channel_name?: string;
}

/** 告警列表分页响应 */
export interface AlertListResponse {
  items: Alert[];
  total: number;
  page: number;
  page_size: number;
}

/** 告警事件服务 */
export const alertService = {
  /** 获取告警列表（支持分页和筛选） */
  list: (params?: Record<string, unknown>) => api.get<AlertListResponse>('/alerts', { params }),
  /** 获取单条告警详情 */
  get: (id: string) => api.get<Alert>(`/alerts/${id}`),
  /** 确认告警 */
  ack: (id: string) => api.post(`/alerts/${id}/ack`),
  /** 获取告警规则列表 */
  listRules: (params?: Record<string, unknown>) => api.get<AlertRule[]>('/alert-rules', { params }),
  /** 创建告警规则 */
  createRule: (data: Partial<AlertRule>) => api.post('/alert-rules', data),
  /** 更新告警规则 */
  updateRule: (id: string, data: Partial<AlertRule>) => api.put(`/alert-rules/${id}`, data),
  /** 删除告警规则 */
  deleteRule: (id: string) => api.delete(`/alert-rules/${id}`),
  /** 手动触发 AlertRule → Prometheus rules.yml 全量同步 */
  syncPromRules: () => api.post('/alert-rules/prometheus/sync'),
  /** 手动触发 Host/Service → Prometheus file_sd 导出 */
  syncPromFileSd: () => api.post('/alert-rules/prometheus/file-sd-sync'),
};

/** PromQL 表达式即时校验响应（走 /promql/query?query=...&time=now）*/
export interface PromQLValidationResult {
  valid: boolean;
  message?: string;
  /** 原始 Prom 数据对象，便于展示 result preview */
  data?: unknown;
}

/**
 * 校验 PromQL 表达式：用 /api/v1/promql/query 跑一次 instant query，
 * HTTP 200 → valid；4xx → 不合法（解析/执行失败）；5xx → 暂不可达。
 * 用 __noToast 关闭全局错误 toast，让编辑器自己展示内联错误。
 */
export async function validatePromQL(expr: string): Promise<PromQLValidationResult> {
  if (!expr || !expr.trim()) {
    return { valid: false, message: '表达式不能为空' };
  }
  try {
    const { data } = await api.get('/promql/query', {
      params: { query: expr },
      // @ts-expect-error 自定义 flag 用于关闭全局错误 toast
      __noToast: true,
    });
    return { valid: true, data };
  } catch (err: unknown) {
    const e = err as { response?: { status?: number; data?: { detail?: string } } };
    const status = e.response?.status;
    const detail = e.response?.data?.detail ?? '未知错误';
    if (status && status >= 400 && status < 500) {
      return { valid: false, message: `解析错误：${detail}` };
    }
    return { valid: false, message: `Prometheus 服务暂不可达（${status ?? 'network'}）` };
  }
}

/** 通知渠道服务 */
export const notificationService = {
  /** 获取所有通知渠道 */
  listChannels: () => api.get<NotificationChannel[]>('/notification-channels'),
  /** 创建通知渠道 */
  createChannel: (data: { name: string; type: string; config: Record<string, unknown>; is_enabled?: boolean }) =>
    api.post<NotificationChannel>('/notification-channels', data),
  /** 更新通知渠道 */
  updateChannel: (id: number, data: Partial<{ name: string; type: string; config: Record<string, unknown>; is_enabled: boolean }>) =>
    api.put<NotificationChannel>(`/notification-channels/${id}`, data),
  /** 删除通知渠道 */
  deleteChannel: (id: number) => api.delete(`/notification-channels/${id}`),
  /** 测试通知渠道发送 */
  testChannel: (id: number) => api.post<{ success: boolean; message: string; channel_type: string; channel_name: string }>(`/notification-channels/${id}/test`),
  /** 获取通知发送日志 */
  listLogs: (params?: Record<string, unknown>) => api.get<NotificationLog[]>('/notification-channels/logs', { params }),
};
