/**
 * AI 运维助手主页面 - Claude Code 终端风格
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { message } from 'antd';
import { useOpsWebSocket, type OpsEvent } from '../hooks/useOpsWebSocket';
import { useAutoScroll } from '../hooks/useAutoScroll';
import { opsApi, type OpsSession } from '../services/opsApi';
import OpsMessageList, { type UiMessage } from '../components/ops/OpsMessageList';
import OpsInputBar from '../components/ops/OpsInputBar';
import OpsSidebar from '../components/ops/OpsSidebar';
import OpsTodoPanel, { type Todo } from '../components/ops/OpsTodoPanel';
import api from '../services/api';

export default function OpsAssistant() {
  const [sessions, setSessions] = useState<OpsSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [todos, setTodos] = useState<Todo[]>([]);
  const [isProcessing, setIsProcessing] = useState(false);
  const [hosts, setHosts] = useState<any[]>([]);
  const [aiConfigs, setAiConfigs] = useState<Array<{ id: string; name: string; feature_key: string; model: string; is_default?: boolean }>>([]);
  const streamingMsgIdRef = useRef<string | null>(null);
  const currentSessionIdRef = useRef<string | null>(null);
  useEffect(() => { currentSessionIdRef.current = currentSessionId; }, [currentSessionId]);
  const { containerRef, resetScroll } = useAutoScroll([messages, isProcessing]);

  useEffect(() => {
    api.get('/hosts?status=online&limit=100')
      .then((r: any) => setHosts(r.data?.items || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    opsApi.listAIConfigs()
      .then((list) => setAiConfigs(list.filter((c) => c.feature_key === 'ops_assistant')))
      .catch(() => setAiConfigs([]));
  }, []);

  const loadSessions = useCallback(async () => {
    try {
      const list = await opsApi.listSessions();
      setSessions(list);
      if (list.length > 0) {
        setCurrentSessionId((prev: string | null) => prev || list[0].id);
      } else {
        const session = await opsApi.createSession();
        setSessions([session]);
        setCurrentSessionId(session.id);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { loadSessions(); }, []);

  useEffect(() => {
    if (!currentSessionId) return;
    setMessages([]);
    setTodos([]);
    streamingMsgIdRef.current = null;
    opsApi.getSession(currentSessionId).then((detail: any) => {
      let latestTodos: Todo[] = [];
      const uiMsgs: UiMessage[] = detail.messages
        .filter((m: any) => m.role !== 'system')
        .map((m: any): UiMessage | null => {
          if (m.role === 'user') return { id: m.id, type: 'user', text: m.content.text || '' };
          if (m.msg_type === 'text') return { id: m.id, type: 'assistant', text: m.content.text || '' };
          if (m.msg_type === 'tool_call') return { id: m.id, type: 'tool_call', toolName: m.content.tool_name, toolArgs: m.content.arguments, toolStatus: 'done' };
          if (m.msg_type === 'command_request') {
            const persistedStatus = m.content.status as ('pending' | 'confirmed' | 'rejected' | 'expired' | undefined);
            return { id: m.id, type: 'command_request', command: m.content.command, hostName: m.content.host_name, reason: m.content.reason, commandStatus: persistedStatus || 'expired' };
          }
          if (m.msg_type === 'ask_user') {
            const status = m.content.status as ('pending' | 'answered' | 'expired' | undefined);
            if (status === 'pending') {
              return { id: m.id, type: 'ask_user', question: m.content.question, inputType: m.content.input_type, options: m.content.options, askStatus: 'pending' };
            }
            const recoveredAnswer = m.content.answer || '（历史会话恢复：该提问已失效，请直接继续提问）';
            return { id: m.id, type: 'ask_user', question: m.content.question, inputType: m.content.input_type, options: m.content.options, askStatus: 'answered', answer: recoveredAnswer };
          }
          if (m.msg_type === 'todo_update') {
            latestTodos = Array.isArray(m.content?.todos) ? m.content.todos : latestTodos;
            return null;
          }
          if (m.msg_type === 'compaction_summary') return { id: m.id, type: 'compaction', summary: m.content.summary };
          return null;
        })
        .filter((m: any): m is UiMessage => m !== null);
      setMessages(uiMsgs);
      setTodos(latestTodos);
    }).catch(() => {});
  }, [currentSessionId]);

  // handleEvent 不依赖任何外部变量（setMessages/setSessions 是稳定引用）
  const handleEvent = useCallback((event: OpsEvent) => {
    console.log('[handleEvent] received:', event);
    switch (event.event) {
      case 'text_delta': {
        console.log('[handleEvent] text_delta, delta:', event.delta, 'streamId:', streamingMsgIdRef.current);
        setMessages((prev: UiMessage[]) => {
          const streamId = streamingMsgIdRef.current;
          if (streamId) {
            const idx = prev.findIndex((m: UiMessage) => m.id === streamId);
            if (idx !== -1) {
              const updated = [...prev];
              updated[idx] = { ...updated[idx], text: (updated[idx].text || '') + event.delta };
              return updated;
            }
          }
          const newId = `stream-${Date.now()}`;
          streamingMsgIdRef.current = newId;
          return [...prev, { id: newId, type: 'assistant', text: event.delta }];
        });
        break;
      }
      case 'tool_start':
        setMessages((prev: UiMessage[]) => [...prev, { id: event.message_id, type: 'tool_call', toolName: event.tool_name, toolArgs: event.arguments, toolStatus: 'running' }]);
        break;
      case 'tool_done':
        setMessages((prev: UiMessage[]) => prev.map((m: UiMessage) => m.id === event.message_id ? { ...m, toolStatus: 'done', toolResult: event.result } : m));
        break;
      case 'tool_error':
        setMessages((prev: UiMessage[]) => prev.map((m: UiMessage) => m.id === event.message_id ? { ...m, toolStatus: 'error', toolError: event.error } : m));
        break;
      case 'command_request':
        setMessages((prev: UiMessage[]) => [
          ...prev,
          { id: event.message_id, type: 'command_request', command: event.command, hostName: event.host_name, reason: event.reason, commandStatus: 'pending' },
          { id: `output-${event.message_id}`, type: 'command_output', outputLines: [], isRunning: false },
        ]);
        break;
      case 'command_output': {
        const outputLine = [event.stdout, event.stderr].filter(Boolean).join('') || '';
        setMessages((prev: UiMessage[]) => prev.map((m: UiMessage) => m.id === `output-${event.message_id}` ? { ...m, outputLines: [...(m.outputLines || []), outputLine], isRunning: true } : m));
        break;
      }
      case 'command_result':
        setMessages((prev: UiMessage[]) => prev.map((m: UiMessage) => {
          if (m.id === `output-${event.message_id}`) return { ...m, isRunning: false, exitCode: event.exit_code, durationMs: event.duration_ms };
          if (m.id === event.message_id) return { ...m, commandStatus: 'confirmed' };
          return m;
        }));
        break;
      case 'command_expired':
        setMessages((prev: UiMessage[]) => prev.map((m: UiMessage) => m.id === event.message_id ? { ...m, commandStatus: 'expired' } : m));
        break;
      case 'ask_user':
        setMessages((prev: UiMessage[]) => [...prev, { id: event.message_id, type: 'ask_user', question: event.question, inputType: event.input_type, options: event.options, askStatus: 'pending' }]);
        break;
      case 'todo_update':
        setTodos(event.todos);
        break;
      case 'compaction':
        setMessages((prev: UiMessage[]) => [...prev, { id: `compact-${Date.now()}`, type: 'compaction', summary: event.summary }]);
        break;
      case 'title_update':
        setSessions((prev: OpsSession[]) => prev.map((s: OpsSession) => s.id === currentSessionIdRef.current ? { ...s, title: event.title } : s));
        break;
      case 'done':
        setIsProcessing(false);
        streamingMsgIdRef.current = null;
        break;
      case 'error':
        setIsProcessing(false);
        message.error(event.message);
        break;
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { sendMessage, confirmCommand, answerQuestion } = useOpsWebSocket({ sessionId: currentSessionId, onEvent: handleEvent });

  const handleSend = useCallback((content: string, hostId?: number, aiConfigId?: string) => {
    if (!currentSessionId || isProcessing) return;
    setIsProcessing(true);
    streamingMsgIdRef.current = null;
    setMessages((prev: UiMessage[]) => [...prev, { id: `user-${Date.now()}`, type: 'user', text: content }]);
    resetScroll();
    sendMessage(content, hostId, aiConfigId);
  }, [currentSessionId, isProcessing, sendMessage, resetScroll]);

  const handleConfirmCommand = useCallback((messageId: string, action: 'confirm' | 'reject') => {
    setMessages((prev: UiMessage[]) => prev.map((m: UiMessage) => m.id === messageId ? { ...m, commandStatus: action === 'confirm' ? 'confirmed' : 'rejected' } : m));
    confirmCommand(messageId, action);
  }, [confirmCommand]);

  const handleAnswerQuestion = useCallback((messageId: string, answer: string) => {
    setMessages((prev: UiMessage[]) => prev.map((m: UiMessage) => m.id === messageId ? { ...m, askStatus: 'answered', answer } : m));
    answerQuestion(messageId, answer);
  }, [answerQuestion]);

  const handleNewSession = async () => {
    try {
      const session = await opsApi.createSession();
      setSessions((prev: OpsSession[]) => [session, ...prev]);
      setCurrentSessionId(session.id);
      setMessages([]);
    } catch { message.error('创建会话失败'); }
  };

  const handleDeleteSession = async (sessionId: string) => {
    try {
      await opsApi.deleteSession(sessionId);
      setSessions((prev: OpsSession[]) => {
        const next = prev.filter((s: OpsSession) => s.id !== sessionId);
        if (sessionId === currentSessionId) {
          if (next.length > 0) {
            setCurrentSessionId(next[0].id);
          } else {
            // 删完了自动新建
            opsApi.createSession().then((s) => {
              setSessions([s]);
              setCurrentSessionId(s.id);
            }).catch(() => {});
          }
        }
        return next;
      });
    } catch { message.error('删除会话失败'); }
  };

  const currentSession = sessions.find((s: OpsSession) => s.id === currentSessionId);

  return (
    <div style={{ height: '100%', minHeight: 0, background: '#0a0a0a', display: 'flex', alignItems: 'stretch', overflow: 'hidden' }}>
      <OpsSidebar
        sessions={sessions}
        currentSessionId={currentSessionId}
        onSelect={(id) => { if (id !== currentSessionId) setCurrentSessionId(id); }}
        onCreate={handleNewSession}
        onDelete={handleDeleteSession}
      />
      <div className="cc-root">
        {todos.length > 0 && (
          <div className="cc-todo-float">
            <OpsTodoPanel todos={todos} />
          </div>
        )}
        <div className="cc-topbar">
          <span className="cc-topbar-model">
            {currentSession?.title ? `/${currentSession.title}` : '/vigilops-ai-ops'}
          </span>
        </div>

        <OpsMessageList
          messages={messages}
          isProcessing={isProcessing}
          onConfirmCommand={handleConfirmCommand}
          onAnswerQuestion={handleAnswerQuestion}
          containerRef={containerRef as React.RefObject<HTMLDivElement>}
        />

        <OpsInputBar onSend={handleSend} disabled={isProcessing} hosts={hosts} aiConfigs={aiConfigs} />

        <div className="cc-statusbar">
          <span className="cc-statusbar-hint">? for shortcuts</span>
          <span className="cc-statusbar-info">
            {isProcessing
              ? <span className="cc-statusbar-thinking">thinking...</span>
              : <span>{sessions.length} session{sessions.length !== 1 ? 's' : ''} · {messages.filter(m => m.type === 'user').length} messages</span>
            }
          </span>
        </div>
      </div>

      <style>{`
        .cc-root {
          display: flex;
          flex-direction: column;
          position: relative;
          flex: 1;
          width: 0;
          background: #111;
          border-left: 1px solid #222;
          overflow: hidden;
          font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
        }
        .cc-todo-float {
          position: absolute;
          right: 14px;
          top: 48px;
          z-index: 2;
          opacity: 0.98;
        }
        .cc-topbar {
          height: 36px;
          padding: 0 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-shrink: 0;
          border-bottom: 1px solid #222;
          background: #0d0d0d;
        }
        .cc-topbar-model {
          font-size: 13px;
          color: #888;
          font-style: italic;
        }
        .cc-statusbar {
          height: 26px;
          padding: 0 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-shrink: 0;
          border-top: 1px solid #222;
          background: #0d0d0d;
        }
        .cc-statusbar-hint { font-size: 12px; color: #555; }
        .cc-statusbar-info { font-size: 12px; color: #666; }
        .cc-statusbar-thinking {
          color: #f0a500;
          animation: cc-blink 1s step-end infinite;
        }
        @keyframes cc-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      `}</style>
    </div>
  );
}
