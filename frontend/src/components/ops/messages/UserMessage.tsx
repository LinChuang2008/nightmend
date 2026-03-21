/**
 * 用户消息 - Claude Code 风格：> text 高亮行
 */

interface UserMessageProps {
  content: string;
}

export default function UserMessage({ content }: UserMessageProps) {
  const lines = content.split('\n');
  return (
    <div className="cc-user-block">
      {lines.map((line, i) => (
        <div key={i} className="cc-user-line">
          <span className="cc-user-prompt">&gt;</span>
          <span className="cc-user-text">{line || '\u00a0'}</span>
        </div>
      ))}
      <style>{`
        .cc-user-block {
          background: #161b22;
          border-left: 3px solid #58a6ff;
          margin: 4px 0;
        }
        .cc-user-line {
          display: flex;
          align-items: baseline;
          gap: 10px;
          padding: 5px 16px;
        }
        .cc-user-prompt {
          color: #58a6ff;
          font-size: 17px;
          flex-shrink: 0;
          font-family: 'SF Mono', 'Fira Code', monospace;
          font-weight: 600;
        }
        .cc-user-text {
          font-size: 17px;
          color: #f0f0f0;
          font-family: 'SF Mono', 'Fira Code', monospace;
          white-space: pre-wrap;
          word-break: break-word;
        }
      `}</style>
    </div>
  );
}
