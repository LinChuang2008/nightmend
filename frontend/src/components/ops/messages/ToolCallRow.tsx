/**
 * 工具调用行 - Claude Code 风格：缩进灰色行
 */
import { useState } from 'react';

interface ToolCallRowProps {
  toolName: string;
  arguments?: Record<string, any>;
  result?: any;
  error?: string;
  status: 'running' | 'done' | 'error';
}

const TOOL_LABELS: Record<string, string> = {
  list_hosts: 'list_hosts',
  get_host_metrics: 'get_host_metrics',
  get_alerts: 'get_alerts',
  search_logs: 'search_logs',
  execute_command: 'execute_command',
  ask_user: 'ask_user',
  update_todo: 'update_todo',
  load_skill: 'load_skill',
  provide_conclusion: 'provide_conclusion',
};

export default function ToolCallRow({ toolName, arguments: args, result, error, status }: ToolCallRowProps) {
  const [expanded, setExpanded] = useState(false);
  const label = TOOL_LABELS[toolName] || toolName;

  // 主要参数摘要（取第一个有意义的参数）
  const argPreview = args
    ? Object.entries(args).map(([k, v]) => `${k}=${typeof v === 'string' ? v : JSON.stringify(v)}`).join(' ')
    : '';

  const statusChar = status === 'running' ? '⠋' : status === 'done' ? '✓' : '✗';
  const statusColor = status === 'running' ? '#f0a500' : status === 'done' ? '#3fb950' : '#f85149';

  return (
    <div className="cc-tool-wrap">
      <div className="cc-tool-row" onClick={() => setExpanded(!expanded)}>
        <span className="cc-tool-status" style={{ color: statusColor, animation: status === 'running' ? 'cc-tool-spin 0.8s steps(8) infinite' : 'none' }}>
          {statusChar}
        </span>
        <span className="cc-tool-name">{label}</span>
        {argPreview && <span className="cc-tool-args">{argPreview}</span>}
        <span className="cc-tool-toggle">{expanded ? '[-]' : '[+]'}</span>
      </div>

      {expanded && (
        <div className="cc-tool-detail">
          {error
            ? <span style={{ color: '#f85149' }}>{error}</span>
            : <pre>{JSON.stringify(result ?? args, null, 2)}</pre>
          }
        </div>
      )}

      <style>{`
        .cc-tool-wrap {
          font-family: 'SF Mono', 'Fira Code', monospace;
        }
        .cc-tool-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 2px 16px 2px 28px;
          cursor: pointer;
          font-size: 16px;
          color: #666;
          transition: color 0.1s;
        }
        .cc-tool-row:hover { color: #888; }
        .cc-tool-status {
          flex-shrink: 0;
          font-size: 12px;
          width: 14px;
        }
        @keyframes cc-tool-spin {
          0%   { content: '⠋'; }
          100% { content: '⠇'; }
        }
        .cc-tool-name {
          color: #888;
          flex-shrink: 0;
        }
        .cc-tool-args {
          color: #555;
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
          flex: 1;
          font-size: 12px;
        }
        .cc-tool-toggle {
          color: #444;
          flex-shrink: 0;
          font-size: 11px;
        }
        .cc-tool-detail {
          margin: 2px 16px 4px 42px;
          padding: 6px 10px;
          background: #111;
          border-left: 2px solid #2a2a2a;
          font-size: 12px;
          color: #666;
          max-height: 160px;
          overflow-y: auto;
          scrollbar-width: none;
        }
        .cc-tool-detail::-webkit-scrollbar { display: none; }
        .cc-tool-detail pre { margin: 0; color: #666; font-family: inherit; }
      `}</style>
    </div>
  );
}
