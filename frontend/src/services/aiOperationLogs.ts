import api from './api';

export interface AIOperationLogItem {
  id: number;
  user_id: number;
  user_name?: string;
  session_id?: string | null;
  request_id?: string | null;
  host_id?: number | null;
  host_name?: string | null;
  command: string;
  reason?: string | null;
  exit_code?: number | null;
  duration_ms?: number | null;
  status: string;
  created_at: string;
}

export interface AIOperationLogParams {
  page?: number;
  page_size?: number;
  user_id?: number;
  host_id?: number;
  status?: string;
}

export function fetchAIOperationLogs(params: AIOperationLogParams = {}) {
  return api.get<{ items: AIOperationLogItem[]; total: number }>('/ai-operation-logs', { params });
}

