/**
 * AI 运维助手 REST API 服务
 */
import api from './api';

export interface OpsSession {
  id: string;
  title: string | null;
  status: string;
  target_host_id: number | null;
  token_count: number;
  created_at: string;
  updated_at: string;
}

export interface OpsMessage {
  id: string;
  session_id: string;
  role: string;
  msg_type: string;
  content: Record<string, any>;
  tool_call_id: string | null;
  created_at: string;
}

export interface OpsSessionDetail extends OpsSession {
  messages: OpsMessage[];
}

export interface SkillInfo {
  name: string;
  description: string;
  triggers: string[];
}

export const opsApi = {
  createSession: (title?: string) =>
    api.post<OpsSession>('/ops/sessions', { title }).then((r) => r.data),

  listSessions: () =>
    api.get<OpsSession[]>('/ops/sessions').then((r) => r.data),

  getSession: (sessionId: string) =>
    api.get<OpsSessionDetail>(`/ops/sessions/${sessionId}`).then((r) => r.data),

  deleteSession: (sessionId: string) =>
    api.delete(`/ops/sessions/${sessionId}`),

  listSkills: () =>
    api.get<SkillInfo[]>('/ops/skills').then((r) => r.data),
};
