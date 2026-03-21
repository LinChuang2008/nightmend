/**
 * 上下文压缩分隔线 - Claude Code 风格
 */
import { useState } from 'react';

interface CompactionDividerProps {
  summary: string;
}

export default function CompactionDivider({ summary }: CompactionDividerProps) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="cc-compact-wrap">
      <div className="cc-compact-line" onClick={() => setExpanded(!expanded)}>
        <span className="cc-compact-text">── context compacted {expanded ? '▾' : '▸'} ──</span>
      </div>
      {expanded && <div className="cc-compact-summary">{summary}</div>}
      <style>{`
        .cc-compact-wrap {
          padding: 6px 0;
          font-family: 'SF Mono', 'Fira Code', monospace;
        }
        .cc-compact-line {
          padding: 2px 16px;
          cursor: pointer;
        }
        .cc-compact-text {
          font-size: 12px;
          color: #3a3a3a;
          transition: color 0.15s;
        }
        .cc-compact-line:hover .cc-compact-text { color: #555; }
        .cc-compact-summary {
          padding: 4px 16px 4px 28px;
          font-size: 12px;
          color: #555;
          line-height: 1.6;
          white-space: pre-wrap;
        }
      `}</style>
    </div>
  );
}
