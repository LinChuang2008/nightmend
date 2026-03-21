/**
 * 消息流 - Claude Code 终端风格
 * 用户消息：> text 高亮行
 * AI 消息：• text 左对齐，无气泡
 */
import React from 'react';
import UserMessage from './messages/UserMessage';
import AssistantMessage from './messages/AssistantMessage';
import ToolCallRow from './messages/ToolCallRow';
import CommandConfirm from './messages/CommandConfirm';
import CommandOutput from './messages/CommandOutput';
import AskUserCard from './messages/AskUserCard';
import CompactionDivider from './messages/CompactionDivider';

export interface UiMessage {
  id: string;
  type: 'user' | 'assistant' | 'tool_call' | 'command_request' | 'command_output' | 'ask_user' | 'compaction' | 'thinking';
  text?: string;
  toolName?: string;
  toolArgs?: Record<string, any>;
  toolResult?: any;
  toolError?: string;
  toolStatus?: 'running' | 'done' | 'error';
  command?: string;
  hostName?: string;
  reason?: string;
  commandStatus?: 'pending' | 'confirmed' | 'rejected' | 'expired';
  outputLines?: string[];
  exitCode?: number;
  durationMs?: number;
  isRunning?: boolean;
  question?: string;
  inputType?: 'radio' | 'checkbox' | 'text';
  options?: string[];
  askStatus?: 'pending' | 'answered';
  answer?: string;
  summary?: string;
}

interface OpsMessageListProps {
  messages: UiMessage[];
  isProcessing: boolean;
  onConfirmCommand: (messageId: string, action: 'confirm' | 'reject') => void;
  onAnswerQuestion: (messageId: string, answer: string) => void;
  containerRef: React.RefObject<HTMLDivElement>;
}

export default function OpsMessageList({ messages, isProcessing, onConfirmCommand, onAnswerQuestion, containerRef }: OpsMessageListProps) {
  const activePendingCommandId = [...messages]
    .reverse()
    .find((m) => m.type === 'command_request' && m.commandStatus === 'pending')
    ?.id;

  return (
    <div ref={containerRef} className="cc-msglist">
      <div className="cc-msglist-inner">
      {messages.length === 0 && !isProcessing && (
        <div className="cc-empty">
          <span className="cc-empty-text">VigilOps AI 运维助手 · 输入问题开始诊断</span>
        </div>
      )}

      {messages.map((msg) => (
        <div key={msg.id}>
          {msg.type === 'user' && <UserMessage content={msg.text || ''} />}
          {msg.type === 'assistant' && <AssistantMessage content={msg.text || ''} />}
          {msg.type === 'tool_call' && (
            <ToolCallRow
              toolName={msg.toolName || ''}
              arguments={msg.toolArgs}
              result={msg.toolResult}
              error={msg.toolError}
              status={msg.toolStatus || 'running'}
            />
          )}
          {msg.type === 'command_request' && (
            <CommandConfirm
              messageId={msg.id}
              command={msg.command || ''}
              hostName={msg.hostName || ''}
              reason={msg.reason}
              status={msg.commandStatus || 'pending'}
              isKeyboardActive={msg.id === activePendingCommandId}
              onConfirm={(id) => onConfirmCommand(id, 'confirm')}
              onReject={(id) => onConfirmCommand(id, 'reject')}
            />
          )}
          {msg.type === 'command_output' && (
            <CommandOutput
              lines={msg.outputLines || []}
              exitCode={msg.exitCode}
              durationMs={msg.durationMs}
              isRunning={msg.isRunning ?? false}
            />
          )}
          {msg.type === 'ask_user' && (
            <AskUserCard
              messageId={msg.id}
              question={msg.question || ''}
              inputType={msg.inputType || 'text'}
              options={msg.options}
              status={msg.askStatus || 'pending'}
              answer={msg.answer}
              onAnswer={onAnswerQuestion}
            />
          )}
          {msg.type === 'compaction' && <CompactionDivider summary={msg.summary || ''} />}
        </div>
      ))}

      {/* 思考中 */}
      {isProcessing && (
        <div className="cc-thinking-row">
          <span className="cc-thinking-cursor">█</span>
        </div>
      )}

      <div style={{ height: 8 }} />
      </div>

      <style>{`
        .cc-msglist {
          flex: 1;
          overflow-y: auto;
          scrollbar-width: thin;
          scrollbar-color: #2a2a2a #0c0c0c;
          font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
        }
        .cc-msglist::-webkit-scrollbar { width: 4px; }
        .cc-msglist::-webkit-scrollbar-track { background: transparent; }
        .cc-msglist::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }
        .cc-msglist-inner {
          max-width: 860px;
          margin: 0 auto;
          padding: 8px 0;
        }
        .cc-empty {
          padding: 40px 16px;
          color: #444;
          font-size: 13px;
        }
        .cc-empty-text { font-style: italic; }
        .cc-thinking-row {
          padding: 4px 16px;
        }
        .cc-thinking-cursor {
          color: #f0a500;
          font-size: 14px;
          animation: cc-cursor-blink 1s step-end infinite;
        }
        @keyframes cc-cursor-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
