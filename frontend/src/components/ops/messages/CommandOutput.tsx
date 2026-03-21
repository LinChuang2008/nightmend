/**
 * 命令输出 - Claude Code 风格：缩进终端输出
 */
interface CommandOutputProps {
  lines: string[];
  exitCode?: number;
  durationMs?: number;
  isRunning: boolean;
}

export default function CommandOutput({ lines, exitCode, durationMs, isRunning }: CommandOutputProps) {
  if (lines.length === 0 && !isRunning) return null;

  return (
    <div className="cc-output-wrap">
      <div className="cc-output-body">
        {lines.map((line, i) => <div key={i}>{line || '\u00a0'}</div>)}
        {isRunning && <span className="cc-output-cursor">█</span>}
      </div>
      {!isRunning && exitCode !== undefined && (
        <div className="cc-output-footer">
          <span className={exitCode === 0 ? 'cc-exit-ok' : 'cc-exit-err'}>
            [exit {exitCode}]
          </span>
          {durationMs !== undefined && (
            <span className="cc-output-dur"> {(durationMs / 1000).toFixed(2)}s</span>
          )}
        </div>
      )}

      <style>{`
        .cc-output-wrap {
          margin: 2px 0;
          font-family: 'SF Mono', 'Fira Code', monospace;
        }
        .cc-output-body {
          padding: 2px 16px 2px 32px;
          font-size: 16px;
          color: #888;
          white-space: pre-wrap;
          overflow-wrap: anywhere;
          max-height: 300px;
          overflow-y: auto;
          scrollbar-width: thin;
          scrollbar-color: #2a2a2a transparent;
          line-height: 1.65;
        }
        .cc-output-body::-webkit-scrollbar { width: 3px; }
        .cc-output-body::-webkit-scrollbar-thumb { background: #2a2a2a; }
        .cc-output-footer {
          padding: 1px 16px 3px 32px;
          font-size: 13px;
        }
        .cc-exit-ok { color: #3fb950; }
        .cc-exit-err { color: #f85149; }
        .cc-output-dur { color: #555; }
        @keyframes cc-out-blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        .cc-output-cursor {
          color: #f0a500;
          animation: cc-out-blink 1s step-end infinite;
        }
      `}</style>
    </div>
  );
}
