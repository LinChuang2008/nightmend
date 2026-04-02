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
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  context_limit_tokens: number;
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

export interface OpsAIConfig {
  id: string;
  feature_key: string;
  name: string;
  base_url: string;
  model: string;
  max_output_tokens: number;
  supports_deep_thinking: boolean;
  deep_thinking_max_tokens: number;
  model_context_tokens: number;
  allowed_context_tokens: number;
  extra_context: string;
  has_api_key: boolean;
  api_key_mask?: string | null;
  is_default: boolean;
  enabled: boolean;
}

export interface OpsAIConfigUpdate {
  feature_key?: string;
  name?: string;
  base_url?: string;
  model?: string;
  api_key?: string;
  max_output_tokens?: number;
  supports_deep_thinking?: boolean;
  deep_thinking_max_tokens?: number;
  model_context_tokens?: number;
  allowed_context_tokens?: number;
  extra_context?: string;
  enabled?: boolean;
}

export interface OpsAIConfigCreate {
  feature_key: string;
  name: string;
  base_url: string;
  model: string;
  api_key?: string;
  max_output_tokens: number;
  supports_deep_thinking: boolean;
  deep_thinking_max_tokens: number;
  model_context_tokens: number;
  allowed_context_tokens: number;
  extra_context?: string;
  enabled?: boolean;
}

export interface OpsAIFeaturePolicy {
  feature_key: string;
  label: string;
  max_models: number;
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

  listAIConfigs: () =>
    api.get<OpsAIConfig[]>('/ops/ai-configs').then((r) => r.data),

  listAIConfigFeatures: () =>
    api.get<OpsAIFeaturePolicy[]>('/ops/ai-config-features').then((r) => r.data),

  listAIConfigsAdmin: () =>
    api.get<OpsAIConfig[]>('/ops/ai-configs/admin').then((r) => r.data),

  createAIConfig: (payload: OpsAIConfigCreate) =>
    api.post<OpsAIConfig>('/ops/ai-configs', payload).then((r) => r.data),

  updateAIConfig: (configId: string, payload: OpsAIConfigUpdate) =>
    api.put<OpsAIConfig>(`/ops/ai-configs/${configId}`, payload).then((r) => r.data),

  deleteAIConfig: (configId: string) =>
    api.delete(`/ops/ai-configs/${configId}`),

  setDefaultAIConfig: (configId: string) =>
    api.post<OpsAIConfig>(`/ops/ai-configs/${configId}/default`).then((r) => r.data),

  importAIConfig: (config: Record<string, unknown>, feature_key?: string, name?: string) =>
    api.post<OpsAIConfig>('/ops/ai-configs/import', { config, feature_key, name }).then((r) => r.data),
};
