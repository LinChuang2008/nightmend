/**
 * 命令确认 - Claude Code 风格：终端内联确认
 */
import { useState, useEffect } from 'react';

interface CommandConfirmProps {
  messageId: string;
  command: string;
  hostName: string;
  reason?: string;
  status: 'pending' | 'confirmed' | 'rejected' | 'expired';
  isKeyboardActive?: boolean;
  onConfirm: (messageId: string) => void;
  onReject: (messageId: string) => void;
}

const TIMEOUT = 60;

export default function CommandConfirm({
  messageId,
  command,
  hostName,
  reason,
  status,
  isKeyboardActive = false,
  onConfirm,
  onReject,
}: CommandConfirmProps) {
  const [remaining, setRemaining] = useState(TIMEOUT);
  const [choice, setChoice] = useState<'confirm' | 'reject'>('confirm');

  useEffect(() => {
    if (status !== 'pending') return;
    const t = setInterval(() => {
      setRemaining((r) => { if (r <= 1) { clearInterval(t); return 0; } return r - 1; });
    }, 1000);
    return () => clearInterval(t);
  }, [status]);

  const isExpired = status === 'expired' || (status === 'pending' && remaining === 0);
  const isDone = status !== 'pending' || isExpired;

  useEffect(() => {
    if (status === 'pending') {
      setChoice('confirm');
    }
  }, [status, messageId]);

  useEffect(() => {
    if (status !== 'pending' || !isKeyboardActive) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (choice === 'confirm') onConfirm(messageId);
        else onReject(messageId);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        onReject(messageId);
        return;
      }
      if (e.key.toLowerCase() === 'y') {
        e.preventDefault();
        setChoice('confirm');
        return;
      }
      if (e.key.toLowerCase() === 'n') {
        e.preventDefault();
        setChoice('reject');
        return;
      }
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight' || e.key === 'Tab') {
        e.preventDefault();
        setChoice((v) => (v === 'confirm' ? 'reject' : 'confirm'));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [status, isKeyboardActive, choice, messageId, onConfirm, onReject]);

  return (
    <div className="cc-cmd-wrap">
      {reason && <div className="cc-cmd-reason">  # {reason}</div>}
      <div className="cc-cmd-line">
        <span className="cc-cmd-host">[{hostName}]</span>
        <span className="cc-cmd-dollar">$</span>
        <span className="cc-cmd-text">{command}</span>
      </div>
      <div className="cc-cmd-actions">
        {isDone ? (
          <span className={`cc-cmd-result ${status === 'confirmed' ? 'ok' : status === 'rejected' ? 'no' : 'exp'}`}>
            {status === 'confirmed' ? '  ✓ executed' : status === 'rejected' ? '  ✗ rejected' : '  ⏱ expired'}
          </span>
        ) : (
          <span className="cc-cmd-prompt">
            <span style={{ color: '#888' }}>  allow? </span>
            <button
              className={`cc-cmd-btn yes ${choice === 'confirm' ? 'active' : ''}`}
              onClick={() => { setChoice('confirm'); onConfirm(messageId); }}
            >
              y
            </button>
            <span style={{ color: '#555' }}>/</span>
            <button
              className={`cc-cmd-btn no ${choice === 'reject' ? 'active' : ''}`}
              onClick={() => { setChoice('reject'); onReject(messageId); }}
            >
              n
            </button>
            <span style={{ color: '#555' }}> ({remaining}s)</span>
            {isKeyboardActive && <span className="cc-cmd-hint"> Enter confirm · Esc reject </span>}
          </span>
        )}
      </div>

      <style>{`
        .cc-cmd-wrap {
          padding: 4px 0;
          font-family: 'SF Mono', 'Fira Code', monospace;
        }
        .cc-cmd-reason {
          padding: 1px 16px;
          font-size: 16px;
          color: #555;
          font-style: italic;
        }
        .cc-cmd-line {
          display: flex;
          align-items: baseline;
          gap: 8px;
          padding: 2px 16px;
          font-size: 17px;
        }
        .cc-cmd-host {
          color: #f0a500;
          flex-shrink: 0;
        }
        .cc-cmd-dollar {
          color: #888;
          flex-shrink: 0;
        }
        .cc-cmd-text {
          color: #e0e0e0;
          white-space: pre-wrap;
          word-break: break-all;
        }
        .cc-cmd-actions {
          padding: 2px 16px;
          font-size: 13px;
        }
        .cc-cmd-result { font-size: 13px; }
        .cc-cmd-result.ok { color: #3fb950; }
        .cc-cmd-result.no { color: #888; }
        .cc-cmd-result.exp { color: #f0a500; }
        .cc-cmd-prompt { display: flex; align-items: center; gap: 4px; }
        .cc-cmd-btn {
          background: transparent;
          border: 1px solid #333;
          color: #ccc;
          font-size: 13px;
          font-family: inherit;
          cursor: pointer;
          padding: 1px 8px;
          transition: all 0.1s;
        }
        .cc-cmd-btn.active.yes { border-color: #3fb950; color: #3fb950; }
        .cc-cmd-btn.active.no { border-color: #f85149; color: #f85149; }
        .cc-cmd-btn.yes:hover { border-color: #3fb950; color: #3fb950; }
        .cc-cmd-btn.no:hover { border-color: #f85149; color: #f85149; }
        .cc-cmd-hint { color: #4f4f4f; margin-left: 8px; }
      `}</style>
    </div>
  );
}
