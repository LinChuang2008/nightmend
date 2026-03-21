/**
 * 会话列表侧边栏 - 铺满左侧，终端风格
 */
import { useState } from 'react';
import type { OpsSession } from '../../services/opsApi';

interface OpsSidebarProps {
  sessions: OpsSession[];
  currentSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onCreate: () => void;
  onDelete: (sessionId: string) => void;
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'just now';
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

export default function OpsSidebar({ sessions, currentSessionId, onSelect, onCreate, onDelete }: OpsSidebarProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null);

  return (
    <div className="ops-sb">
      <div className="ops-sb-header">
        <span className="ops-sb-title">~ sessions</span>
        <button className="ops-sb-new" onClick={onCreate} title="新建会话">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
            <path d="M7 1v12M1 7h12" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round"/>
          </svg>
          <span>new</span>
        </button>
      </div>

      <div className="ops-sb-list">
        {sessions.length === 0 && (
          <div className="ops-sb-empty">no sessions yet</div>
        )}
        {sessions.map((session) => {
          const isActive = session.id === currentSessionId;
          const isHovered = hoveredId === session.id;
          const title = session.title || 'new session';
          const time = session.updated_at ? timeAgo(session.updated_at) : '';

          return (
            <div
              key={session.id}
              className={`ops-sb-item ${isActive ? 'active' : ''}`}
              onClick={() => onSelect(session.id)}
              onMouseEnter={() => setHoveredId(session.id)}
              onMouseLeave={() => setHoveredId(null)}
            >
              <div className="ops-sb-item-top">
                <span className="ops-sb-item-indicator">{isActive ? '▶' : '·'}</span>
                <span className="ops-sb-item-title">{title}</span>
                {isHovered && (
                  <button
                    className="ops-sb-del"
                    onClick={(e) => { e.stopPropagation(); onDelete(session.id); }}
                    title="删除"
                  >
                    <svg width="11" height="11" viewBox="0 0 10 10" fill="none">
                      <path d="M1 1l8 8M9 1L1 9" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                    </svg>
                  </button>
                )}
              </div>
              <div className="ops-sb-item-time">{time}</div>
            </div>
          );
        })}
      </div>

      <style>{`
        .ops-sb {
          width: 300px;
          min-width: 300px;
          border-right: 1px solid #222;
          display: flex;
          flex-direction: column;
          background: #0d0d0d;
          flex-shrink: 0;
          overflow: hidden;
          font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
          height: 100%;
        }
        .ops-sb-header {
          height: 44px;
          padding: 0 14px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          border-bottom: 1px solid #222;
          flex-shrink: 0;
        }
        .ops-sb-title {
          font-size: 17px;
          color: #666;
          letter-spacing: 0.03em;
        }
        .ops-sb-new {
          display: flex;
          align-items: center;
          gap: 5px;
          height: 32px;
          padding: 0 14px;
          border-radius: 5px;
          border: 1px solid #2e2e2e;
          background: transparent;
          color: #888;
          font-size: 15px;
          font-family: inherit;
          cursor: pointer;
          transition: all 0.15s;
        }
        .ops-sb-new:hover {
          background: #1c1c1c;
          color: #ddd;
          border-color: #444;
        }
        .ops-sb-list {
          flex: 1;
          overflow-y: auto;
          scrollbar-width: thin;
          scrollbar-color: #2a2a2a transparent;
          padding: 6px 0;
        }
        .ops-sb-list::-webkit-scrollbar { width: 3px; }
        .ops-sb-list::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 2px; }
        .ops-sb-empty {
          padding: 20px 16px;
          font-size: 13px;
          color: #444;
          font-style: italic;
        }
        .ops-sb-item {
          padding: 11px 16px;
          cursor: pointer;
          border-left: 2px solid transparent;
          transition: background 0.1s;
        }
        .ops-sb-item:hover { background: #161616; }
        .ops-sb-item.active {
          background: #181818;
          border-left-color: #3fb950;
        }
        .ops-sb-item-top {
          display: flex;
          align-items: center;
          gap: 7px;
        }
        .ops-sb-item-indicator {
          font-size: 9px;
          color: #3fb950;
          flex-shrink: 0;
          width: 12px;
          text-align: center;
        }
        .ops-sb-item:not(.active) .ops-sb-item-indicator {
          color: #333;
          font-size: 12px;
        }
        .ops-sb-item-title {
          font-size: 17px;
          color: #888;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
          flex: 1;
          min-width: 0;
        }
        .ops-sb-item:hover .ops-sb-item-title { color: #bbb; }
        .ops-sb-item.active .ops-sb-item-title {
          color: #f0f0f0;
        }
        .ops-sb-item-time {
          font-size: 13px;
          color: #444;
          padding-left: 19px;
          margin-top: 3px;
        }
        .ops-sb-item:hover .ops-sb-item-time { color: #555; }
        .ops-sb-item.active .ops-sb-item-time { color: #555; }
        .ops-sb-del {
          background: transparent;
          border: none;
          color: #444;
          cursor: pointer;
          padding: 2px;
          display: flex;
          align-items: center;
          border-radius: 3px;
          flex-shrink: 0;
          transition: color 0.1s;
          margin-left: auto;
        }
        .ops-sb-del:hover { color: #ff6b6b; }
      `}</style>
    </div>
  );
}
