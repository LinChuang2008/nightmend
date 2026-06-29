/**
 * Axios 实例配置模块
 *
 * 统一处理：
 *   - 401 → 清前端缓存 + 重定向登录
 *   - 429 → toast 提示限流，不重试
 *   - 网络错误 + 幂等 GET 5xx → 指数退避自动重试最多 2 次
 *   - 其他 5xx → toast 通用错误
 *
 * JWT 已迁移至 httpOnly Cookie，浏览器自动携带（withCredentials: true）。
 */
import axios, {
  type AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
  type InternalAxiosRequestConfig,
} from 'axios';
import { message } from 'antd';

/** 创建 Axios 实例，统一配置基础路径、超时和请求头 */
const api = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

/**
 * AI 专用 Axios 实例：超时设为 60s
 * AI 分析/Chat 接口响应时间较长（20-30s），需要单独配置
 */
export const aiApi = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
});

// 幂等 GET 请求的重试上限，指数退避避免雪崩
const MAX_RETRY = 2;
const RETRY_BASE_MS = 400;

// 5xx 但有可能通过重试恢复的场景：GET 视作幂等重试，其他方法不重试
const RETRY_STATUS = new Set([502, 503, 504]);

interface RetryableConfig extends InternalAxiosRequestConfig {
  __retryCount?: number;
  __noToast?: boolean;
}

/** 显示 toast；同一 key 节流 3s，防止风暴 */
const lastToastAt = new Map<string, number>();
function toastOnce(key: string, text: string, type: 'error' | 'warning' = 'error') {
  const now = Date.now();
  const prev = lastToastAt.get(key) ?? 0;
  if (now - prev < 3000) return;
  lastToastAt.set(key, now);
  if (type === 'error') message.error(text);
  else message.warning(text);
}

function shouldRetry(error: AxiosError): boolean {
  const cfg = error.config as RetryableConfig | undefined;
  if (!cfg) return false;
  if (cfg.method && cfg.method.toLowerCase() !== 'get') return false;
  const count = cfg.__retryCount ?? 0;
  if (count >= MAX_RETRY) return false;
  // 网络错误（无 response）或 5xx 网关级错误
  if (!error.response) return true;
  return RETRY_STATUS.has(error.response.status);
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function handleError(error: AxiosError, instance: AxiosInstance): Promise<unknown> {
  const cfg = error.config as RetryableConfig | undefined;

  // 401 统一清缓存 + 跳转
  if (error.response?.status === 401) {
    localStorage.removeItem('user_name');
    localStorage.removeItem('user_role');
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }

  // 幂等 GET 重试
  if (cfg && shouldRetry(error)) {
    const count = (cfg.__retryCount ?? 0) + 1;
    cfg.__retryCount = count;
    const backoff = RETRY_BASE_MS * 2 ** (count - 1);
    await delay(backoff);
    return instance.request(cfg);
  }

  // 组件可通过 { __noToast: true } 关闭全局提示，自己定制错误展示
  if (!cfg?.__noToast) {
    const status = error.response?.status;
    if (status === 429) {
      toastOnce('rate_limit', '请求过于频繁，请稍后重试', 'warning');
    } else if (status === 403) {
      toastOnce('forbidden', '权限不足');
    } else if (status && status >= 500) {
      toastOnce('server_error', '服务暂时不可用，请稍后重试');
    } else if (!error.response) {
      // 超时或网络中断，避免和重试成功后的场景冲突
      toastOnce('network', '网络异常，请检查连接');
    }
  }

  return Promise.reject(error);
}

api.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => handleError(error, api),
);
aiApi.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => handleError(error, aiApi),
);

/** 辅助类型：业务层需要关闭全局 toast 时透传 */
export type SilentRequestConfig = AxiosRequestConfig & { __noToast?: boolean };

export default api;
