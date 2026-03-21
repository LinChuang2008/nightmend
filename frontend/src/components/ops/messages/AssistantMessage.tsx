/**
 * AI 消息 - Claude Code 风格：• 开头，等宽字体，无气泡
 */
import { type ReactNode } from 'react';

interface AssistantMessageProps {
  content: string;
}

function renderInline(text: string): ReactNode[] {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, idx) => {
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) {
      return <code key={idx} className="cc-inline-code">{part.slice(1, -1)}</code>;
    }
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={idx} style={{ color: '#ffffff' }}>{part.slice(2, -2)}</strong>;
    }
    return part;
  });
}

function renderMarkdown(text: string): ReactNode[] {
  const lines = text.split('\n');
  const elements: ReactNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith('```')) {
      const lang = line.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith('```')) {
        codeLines.push(lines[i]);
        i++;
      }
      elements.push(
        <div key={`cb-${i}`} className="cc-codeblock">
          {lang && <div className="cc-codeblock-lang">{lang}</div>}
          <pre><code>{codeLines.join('\n')}</code></pre>
        </div>
      );
      i++;
      continue;
    }

    if (line.startsWith('### ') || line.startsWith('## ') || line.startsWith('# ')) {
      const txt = line.replace(/^#+\s/, '');
      elements.push(
        <div key={i} className="cc-ai-line cc-heading">
          <span className="cc-bullet">§</span>
          <span>{renderInline(txt)}</span>
        </div>
      );
    } else if (line.startsWith('- ') || line.startsWith('* ')) {
      elements.push(
        <div key={i} className="cc-ai-line cc-list-item">
          <span className="cc-list-dash">-</span>
          <span>{renderInline(line.slice(2))}</span>
        </div>
      );
    } else if (/^\d+\. /.test(line)) {
      const match = line.match(/^(\d+)\. (.*)$/);
      if (match) {
        elements.push(
          <div key={i} className="cc-ai-line cc-list-item">
            <span className="cc-list-dash">{match[1]}.</span>
            <span>{renderInline(match[2])}</span>
          </div>
        );
      }
    } else if (line.trim() === '') {
      elements.push(<div key={i} className="cc-ai-spacer" />);
    } else {
      elements.push(
        <div key={i} className="cc-ai-line">
          <span className="cc-bullet">•</span>
          <span>{renderInline(line)}</span>
        </div>
      );
    }
    i++;
  }
  return elements;
}

export default function AssistantMessage({ content }: AssistantMessageProps) {
  if (!content) return null;
  return (
    <div className="cc-assistant-block">
      {renderMarkdown(content)}
      <style>{`
        .cc-assistant-block {
          padding: 6px 0 4px;
          font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
        }
        .cc-ai-line {
          display: flex;
          align-items: baseline;
          gap: 10px;
          padding: 2px 16px;
          font-size: 17px;
          line-height: 1.8;
          color: #e2e2e2;
        }
        .cc-ai-spacer { height: 8px; }
        .cc-bullet {
          color: #3fb950;
          flex-shrink: 0;
          font-size: 15px;
        }
        .cc-heading {
          color: #ffffff;
          font-weight: 600;
          font-size: 18px;
        }
        .cc-heading .cc-bullet {
          color: #58a6ff;
          font-size: 14px;
        }
        .cc-list-item {
          padding-left: 28px !important;
        }
        .cc-list-dash {
          color: #3fb950;
          flex-shrink: 0;
          min-width: 18px;
        }
        .cc-inline-code {
          font-family: inherit;
          font-size: 15px;
          color: #79c0ff;
          background: #1a1f2e;
          padding: 1px 6px;
          border-radius: 3px;
          border: 1px solid #2a3a5a;
        }
        .cc-codeblock {
          margin: 10px 16px;
          background: #0d1117;
          border: 1px solid #2a2a2a;
          border-left: 3px solid #3fb950;
          border-radius: 0 4px 4px 0;
        }
        .cc-codeblock-lang {
          font-size: 11px;
          color: #3fb950;
          padding: 4px 12px 3px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          border-bottom: 1px solid #1e1e1e;
          background: #111;
        }
        .cc-codeblock pre {
          margin: 0;
          padding: 12px 14px;
          overflow-x: auto;
          scrollbar-width: thin;
          scrollbar-color: #333 transparent;
        }
        .cc-codeblock pre::-webkit-scrollbar { height: 3px; }
        .cc-codeblock pre::-webkit-scrollbar-thumb { background: #333; }
        .cc-codeblock code {
          font-family: inherit;
          font-size: 15px;
          color: #e2e2e2;
          white-space: pre;
        }
      `}</style>
    </div>
  );
}
