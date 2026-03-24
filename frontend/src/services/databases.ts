/**
 * 数据库监控服务模块
 * 提供数据库列表、详情、性能指标和慢查询的 API 调用
 */
import api from './api';

/** 数据库实例 */
export interface DatabaseItem {
  id: number;
  /** 所属主机 ID */
  host_id: number;
  /** 数据库名称 */
  name: string;
  /** 数据库类型（mysql / postgresql / oracle 等） */
  db_type: string;
  /** 运行状态 */
  status: string;
  created_at: string | null;
  updated_at: string | null;
  /** 最新性能指标快照 */
  latest_metrics?: {
    /** 总连接数 */
    connections_total: number | null;
    /** 活跃连接数 */
    connections_active: number | null;
    /** 数据库大小（MB） */
    database_size_mb: number | null;
    /** 慢查询数量 */
    slow_queries: number | null;
    /** 表数量 */
    tables_count: number | null;
    /** 已提交事务数 */
    transactions_committed: number | null;
    /** 已回滚事务数 */
    transactions_rolled_back: number | null;
    /** 每秒查询数 */
    qps: number | null;
    /** 表空间使用率（%） */
    tablespace_used_pct: number | null;
    /** 记录时间 */
    recorded_at: string | null;
  };
}

/** 慢查询记录 */
export interface SlowQuery {
  /** SQL 标识 */
  sql_id: string;
  /** 平均执行时间（秒） */
  avg_seconds: number;
  /** 执行次数 */
  executions: number;
  /** SQL 语句内容 */
  sql_text: string;
}

/** 慢查询响应 */
export interface SlowQueriesResponse {
  database_id: number;
  slow_queries: SlowQuery[];
}

/** 数据库性能指标 */
export interface DatabaseMetric {
  connections_total: number | null;
  connections_active: number | null;
  database_size_mb: number | null;
  slow_queries: number | null;
  tables_count: number | null;
  transactions_committed: number | null;
  transactions_rolled_back: number | null;
  qps: number | null;
  tablespace_used_pct: number | null;
  recorded_at: string | null;
}

/** 数据库列表响应 */
export interface DatabaseListResponse {
  databases: DatabaseItem[];
  total: number;
}

/** 数据库指标历史响应 */
export interface DatabaseMetricsResponse {
  database_id: number;
  /** 查询时间范围（如 1h / 24h / 7d） */
  period: string;
  metrics: DatabaseMetric[];
}

export interface DatabaseTargetItem {
  id: number;
  host_id: number;
  host_name: string;
  name: string;
  db_type: string;
  db_host: string;
  db_port: number;
  db_name: string;
  username: string;
  has_password: boolean;
  interval_sec: number;
  connect_timeout_sec: number;
  is_active: boolean;
  extra_config?: Record<string, unknown> | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface DatabaseTargetListResponse {
  items: DatabaseTargetItem[];
  total: number;
}

export interface DatabaseTargetPayload {
  host_id: number;
  name: string;
  db_type: string;
  db_host: string;
  db_port: number;
  db_name: string;
  username: string;
  password: string;
  interval_sec: number;
  connect_timeout_sec: number;
  is_active: boolean;
  extra_config?: Record<string, unknown> | null;
}

/** 数据库服务 */
export const databaseService = {
  /** 获取数据库列表 */
  list: (params?: Record<string, unknown>) => api.get<DatabaseListResponse>('/databases', { params }),
  /** 获取单个数据库详情 */
  get: (id: number | string) => api.get<DatabaseItem>(`/databases/${id}`),
  /** 获取数据库性能指标历史（默认最近 1 小时） */
  getMetrics: (id: number | string, period = '1h') => api.get<DatabaseMetricsResponse>(`/databases/${id}/metrics`, { params: { period } }),
  /** 获取慢查询列表 */
  getSlowQueries: (id: number | string) => api.get<SlowQueriesResponse>(`/databases/${id}/slow-queries`),
  /** 获取数据库监控目标（管理端） */
  listTargets: (params?: Record<string, unknown>) => api.get<DatabaseTargetListResponse>('/databases/targets', { params }),
  /** 新增数据库监控目标（管理端） */
  createTarget: (data: DatabaseTargetPayload) => api.post<{ id: number }>('/databases/targets', data),
  /** 更新数据库监控目标（管理端） */
  updateTarget: (id: number, data: Partial<DatabaseTargetPayload>) => api.put('/databases/targets/' + id, data),
  /** 删除（停用）数据库监控目标（管理端） */
  deleteTarget: (id: number) => api.delete('/databases/targets/' + id),
};
