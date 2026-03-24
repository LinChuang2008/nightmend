/**
 * Ops WebSocket 连接管理 Hook
 * 用 ref 保存最新 onEvent，避免因回调变化触发重连
 */
import { useEffect, useRef, useCallback } from 'react';

export type OpsEvent =
  | { event: 'text_delta'; delta: string }
  | { event: 'tool_start'; message_id: string; tool_name: string; arguments: Record<string, any> }
  | { event: 'tool_done'; message_id: string; tool_name: string; result: any }
  | { event: 'tool_error'; message_id: string; tool_name: string; error: string }
  | { event: 'command_request'; message_id: string; command: string; host_id: number; host_name: string; timeout: number; reason?: string }
  | { event: 'command_output'; message_id: string; stdout: string; stderr: string }
  | { event: 'command_result'; message_id: string; exit_code: number; duration_ms: number }
  | { event: 'command_expired'; message_id: string; reason: string }
  | { event: 'ask_user'; message_id: string; question: string; input_type: 'radio' | 'checkbox' | 'text'; options?: string[] }
  | { event: 'todo_update'; todos: Array<{ id: string; text: string; status: 'pending' | 'in_progress' | 'done' }> }
  | { event: 'compaction'; summary: string }
  | { event: 'title_update'; title: string }
  | { event: 'done' }
  | { event: 'error'; message: string };

interface UseOpsWebSocketOptions {
  sessionId: string | null;
  onEvent: (event: OpsEvent) => void;
}

export function useOpsWebSocket({ sessionId, onEvent }: UseOpsWebSocketOptions) {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  const shouldReconnectRef = useRef(true);
  // 始终保存最新的 onEvent，不触发重连
  const onEventRef = useRef(onEvent);
  useEffect(() => { onEventRef.current = onEvent; }, [onEvent]);

  useEffect(() => {
    mountedRef.current = true;
    shouldReconnectRef.current = true;

    const connect = () => {
      if (!sessionId || !mountedRef.current) return;

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const url = `${protocol}//${window.location.host}/api/v1/ops/ws/${sessionId}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onmessage = (e) => {
        console.log('[WS] raw message:', e.data);
        try {
          const event = JSON.parse(e.data) as OpsEvent;
          // 后端心跳响应，不属于 OpsEvent 业务事件
          if ((event as any).type === 'pong') return;
          console.log('[WS] parsed event:', event);
          if (mountedRef.current) {
            console.log('[WS] calling onEvent, mounted=true');
            onEventRef.current(event);
          } else {
            console.warn('[WS] onEvent skipped, mounted=false');
          }
        } catch (err) {
          console.error('[WS] parse error:', err, 'raw:', e.data);
        }
      };

      // 心跳：每 20 秒发一次 ping，防止 nginx/代理超时断开
      const heartbeatTimer = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, 20000);

      ws.onclose = (evt) => {
        clearInterval(heartbeatTimer);
        // 1008: token/session 校验失败，不继续重连，避免无限刷连接日志
        const shouldRetry =
          mountedRef.current &&
          shouldReconnectRef.current &&
          evt.code !== 1008 &&
          evt.code !== 4401 &&
          evt.code !== 4403;
        if (shouldRetry) {
          reconnectTimerRef.current = setTimeout(connect, 3000);
        }
      };

      ws.onerror = () => { if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) ws.close(); };
    };

    connect();

    return () => {
      mountedRef.current = false;
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  // 只在 sessionId 变化时重建连接
  }, [sessionId]);

  const send = useCallback((data: object) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  const sendMessage = useCallback((content: string, hostId?: number, aiConfigId?: string) => {
    send({ type: 'user_message', content, host_id: hostId ?? null, ai_config_id: aiConfigId ?? null });
  }, [send]);

  const confirmCommand = useCallback((messageId: string, action: 'confirm' | 'reject') => {
    send({
      type: 'approval_reply',
      message_id: messageId,
      request_type: 'command_request',
      action,
    });
  }, [send]);

  const answerQuestion = useCallback((messageId: string, answer: string) => {
    send({
      type: 'approval_reply',
      message_id: messageId,
      request_type: 'ask_user',
      action: 'answer',
      answer,
    });
  }, [send]);

  return { sendMessage, confirmCommand, answerQuestion };
}
