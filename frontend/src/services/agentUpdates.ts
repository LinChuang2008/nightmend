/**
 * Agent 更新相关 API 服务
 */
import api from './api';

export interface AgentVersion {
  version: string;
  wheel_files: string[];
  created_at: string;
}

export interface BuildResult {
  success: boolean;
  message?: string;
  wheel_path?: string;
  version?: string;
  download_url?: string;
}

export interface TriggerResult {
  status: string;
  message: string;
}

const agentUpdateService = {
  /**
   * 获取可用版本列表
   */
  async listVersions(): Promise<{ data: { versions: AgentVersion[] } }> {
    return api.get('/agent-updates/list');
  },

  /**
   * 构建 wheel 包
   */
  async buildWheel(version: string): Promise<{ data: BuildResult }> {
    return api.post(`/agent-updates/build/${version}`);
  },

  /**
   * 触发 Agent 更新
   */
  async triggerUpdate(hostId: number | string): Promise<{ data: TriggerResult }> {
    return api.post(`/agent/trigger-update/${hostId}`);
  },
};

export default agentUpdateService;
