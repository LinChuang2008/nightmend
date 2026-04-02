/**
 * 输入栏 - Claude Code 风格：> 提示符 + 光标
 */
import React, { useMemo, useState, useRef } from 'react';

const DEFAULT_AI_CONFIG_ID = '__default__';

interface Host {
  id: number;
  hostname: string;
  display_name?: string;
  status: string;
  last_heartbeat?: string;
  created_at?: string;
}

interface OpsInputBarProps {
  onSend: (content: string, hostId?: number, aiConfigId?: string, useDeepThinking?: boolean) => void;
  disabled?: boolean;
  pendingAskQuestion?: string;
  onActiveModelChange?: (model: string) => void;
  onActiveContextLimitChange?: (tokens: number) => void;
  hosts?: Host[];
  aiConfigs?: Array<{
    id: string;
    name: string;
    feature_key: string;
    model: string;
    is_default?: boolean;
    supports_deep_thinking?: boolean;
    deep_thinking_max_tokens?: number;
    allowed_context_tokens?: number;
  }>;
}

export default function OpsInputBar({ onSend, disabled, pendingAskQuestion, onActiveModelChange, onActiveContextLimitChange, hosts = [], aiConfigs = [] }: OpsInputBarProps) {
  const [value, setValue] = useState('');
  const [selectedHostId, setSelectedHostId] = useState<number | undefined>();
  const [selectedAiConfigId, setSelectedAiConfigId] = useState<string>(DEFAULT_AI_CONFIG_ID);
  const [useDeepThinking, setUseDeepThinking] = useState(false);
  const [showHostPicker, setShowHostPicker] = useState(false);
  const [searchText, setSearchText] = useState('');
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const isAnswerMode = Boolean(pendingAskQuestion);

  const selectedHost = hosts.find((h) => Number(h.id) === selectedHostId);

  const commonHosts = useMemo(() => {
    const toTime = (h: Host) => {
      const raw = h.last_heartbeat || h.created_at;
      const ts = raw ? new Date(raw).getTime() : 0;
      return Number.isNaN(ts) ? 0 : ts;
    };
    return [...hosts]
      .filter((h) => h.status === 'online')
      .sort((a, b) => toTime(b) - toTime(a))
      .slice(0, 5);
  }, [hosts]);

  const filteredHosts = useMemo(() => {
    const keyword = searchText.trim().toLowerCase();
    if (!keyword) return hosts;
    return hosts.filter((h) => {
      const name = (h.display_name || h.hostname || '').toLowerCase();
      return name.includes(keyword);
    });
  }, [hosts, searchText]);

  React.useEffect(() => {
    if (selectedAiConfigId === DEFAULT_AI_CONFIG_ID) return;
    const exists = aiConfigs.some((c) => c.id === selectedAiConfigId);
    if (!exists) setSelectedAiConfigId(DEFAULT_AI_CONFIG_ID);
  }, [aiConfigs, selectedAiConfigId]);

  const resolvedAiConfig = selectedAiConfigId === DEFAULT_AI_CONFIG_ID
    ? (aiConfigs.find((c) => c.is_default) || aiConfigs[0])
    : aiConfigs.find((c) => c.id === selectedAiConfigId);
  const selectedAiConfig = resolvedAiConfig;
  const deepThinkingSupported = Boolean(selectedAiConfig?.supports_deep_thinking);

  React.useEffect(() => {
    onActiveModelChange?.(selectedAiConfig?.model || '');
  }, [onActiveModelChange, selectedAiConfig?.model]);

  React.useEffect(() => {
    const limit = Number(selectedAiConfig?.allowed_context_tokens || 0);
    if (limit > 0) onActiveContextLimitChange?.(limit);
  }, [onActiveContextLimitChange, selectedAiConfig?.allowed_context_tokens]);

  React.useEffect(() => {
    if (!deepThinkingSupported && useDeepThinking) {
      setUseDeepThinking(false);
    }
  }, [deepThinkingSupported, useDeepThinking]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled || (!isAnswerMode && !selectedHostId)) return;
    const aiConfigId = selectedAiConfigId === DEFAULT_AI_CONFIG_ID ? undefined : selectedAiConfigId;
    if (isAnswerMode) {
      onSend(trimmed);
    } else {
      onSend(trimmed, selectedHostId, aiConfigId, deepThinkingSupported && useDeepThinking);
    }
    setValue('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleInput = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setValue(e.target.value);
    const el = e.target;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 200) + 'px';
  };

  return (
    <div className="cc-input-wrap">
      <div className="cc-host-row">
        <span className="cc-host-label">ai:</span>
        <select
          className="cc-ai-select"
          value={selectedAiConfigId}
          onChange={(e) => setSelectedAiConfigId(e.target.value)}
        >
          <option value={DEFAULT_AI_CONFIG_ID}>默认模型配置（自动回退）</option>
          {aiConfigs.map((cfg) => (
            <option key={cfg.id} value={cfg.id}>
              {cfg.name} ({cfg.feature_key}) · {cfg.model}
            </option>
          ))}
        </select>
        <label className={`cc-think-toggle ${deepThinkingSupported ? '' : 'disabled'}`}>
          <input
            type="checkbox"
            checked={deepThinkingSupported && useDeepThinking}
            disabled={!deepThinkingSupported}
            onChange={(e) => setUseDeepThinking(e.target.checked)}
          />
          <span>深度思考</span>
        </label>
        {selectedAiConfig ? (
          <span className="cc-ai-hint">
            feature={selectedAiConfig.feature_key}
            {selectedAiConfig.supports_deep_thinking ? ` · deep=${selectedAiConfig.deep_thinking_max_tokens || 0}` : ''}
          </span>
        ) : (
          <span className="cc-ai-hint">feature=default</span>
        )}
      </div>

      {/* 主机选择器行 */}
      {hosts.length > 0 && (
        <div className="cc-host-row">
          <span className="cc-host-label">target:</span>
          <button
            className="cc-host-btn"
            onClick={() => setShowHostPicker(!showHostPicker)}
            type="button"
          >
            {selectedHost ? (selectedHost.display_name || selectedHost.hostname) : '未选择主机'}
            {selectedHostId && (
              <span
                className="cc-host-clear"
                onClick={(e) => { e.stopPropagation(); setSelectedHostId(undefined); setShowHostPicker(false); }}
              > [x]</span>
            )}
          </button>

          {showHostPicker && (
            <div className="cc-host-picker">
              <div className="cc-host-search-wrap">
                <input
                  className="cc-host-search"
                  value={searchText}
                  onChange={(e) => setSearchText(e.target.value)}
                  placeholder="搜索主机..."
                />
              </div>

              {searchText.trim() === '' && commonHosts.length > 0 && (
                <>
                  <div className="cc-host-group-title">常用主机（5）</div>
                  {commonHosts.map((h) => (
                    <div
                      key={`common-${h.id}`}
                      className={`cc-host-option ${Number(h.id) === selectedHostId ? 'active' : ''} ${h.status !== 'online' ? 'offline' : ''}`}
                      onClick={() => { if (h.status === 'online') { setSelectedHostId(Number(h.id)); setShowHostPicker(false); } }}
                    >
                      <span className={`cc-host-status ${h.status === 'online' ? 'on' : ''}`}>●</span>
                      {h.display_name || h.hostname}
                    </div>
                  ))}
                  <div className="cc-host-divider" />
                </>
              )}

              <div className="cc-host-group-title">{searchText.trim() ? '搜索结果' : '全部主机'}</div>
              {filteredHosts.length === 0 && (
                <div className="cc-host-empty">未找到匹配主机</div>
              )}
              {filteredHosts.map((h) => (
                <div
                  key={h.id}
                  className={`cc-host-option ${Number(h.id) === selectedHostId ? 'active' : ''} ${h.status !== 'online' ? 'offline' : ''}`}
                  onClick={() => { if (h.status === 'online') { setSelectedHostId(Number(h.id)); setShowHostPicker(false); } }}
                >
                  <span className={`cc-host-status ${h.status === 'online' ? 'on' : ''}`}>●</span>
                  {h.display_name || h.hostname}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 输入行 */}
      <div className={`cc-input-line ${disabled ? 'disabled' : ''}`}>
        <span className="cc-prompt">&gt;</span>
        <textarea
          ref={textareaRef}
          className="cc-textarea"
          value={value}
          onChange={handleInput}
          onKeyDown={handleKeyDown}
          placeholder={isAnswerMode ? '输入对当前问题的答复，回车发送' : ''}
          disabled={disabled}
          rows={1}
          autoFocus
        />
        {disabled && <span className="cc-input-spinner">⠋</span>}
      </div>
      {!isAnswerMode && !selectedHostId && (
        <div className="cc-host-required">请先选择目标主机后再发送</div>
      )}
      {isAnswerMode && (
        <div className="cc-answer-hint">等待你的答复: {pendingAskQuestion}</div>
      )}

      <style>{`
        .cc-input-wrap {
          border-top: 1px solid #222;
          background: #0d0d0d;
          flex-shrink: 0;
          font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
        }
        .cc-host-row {
          display: flex;
          align-items: center;
          gap: 8px;
          padding: 5px 16px 0;
          position: relative;
        }
        .cc-host-label {
          font-size: 12px;
          color: #666;
        }
        .cc-host-btn {
          background: transparent;
          border: none;
          color: #999;
          font-size: 12px;
          font-family: inherit;
          cursor: pointer;
          padding: 0;
          transition: color 0.1s;
        }
        .cc-host-btn:hover { color: #ddd; }
        .cc-ai-select {
          background: #111;
          color: #ddd;
          border: 1px solid #2a2a2a;
          height: 24px;
          font-size: 12px;
          font-family: inherit;
        }
        .cc-ai-hint {
          color: #666;
          font-size: 11px;
        }
        .cc-think-toggle {
          display: inline-flex;
          align-items: center;
          gap: 6px;
          color: #bbb;
          font-size: 12px;
          user-select: none;
          white-space: nowrap;
        }
        .cc-think-toggle.disabled {
          color: #555;
        }
        .cc-think-toggle input {
          accent-color: #f0a500;
        }
        .cc-host-clear { color: #f85149; }
        .cc-host-picker {
          position: absolute;
          bottom: calc(100% + 4px);
          left: 60px;
          background: #161616;
          border: 1px solid #2e2e2e;
          min-width: 260px;
          max-height: 280px;
          overflow-y: auto;
          z-index: 50;
          scrollbar-width: none;
        }
        .cc-host-search-wrap {
          padding: 8px;
          border-bottom: 1px solid #232323;
          position: sticky;
          top: 0;
          background: #161616;
          z-index: 1;
        }
        .cc-host-search {
          width: 100%;
          height: 28px;
          background: #111;
          border: 1px solid #2a2a2a;
          color: #ddd;
          outline: none;
          padding: 0 8px;
          font-size: 12px;
          font-family: inherit;
        }
        .cc-host-group-title {
          padding: 6px 12px 4px;
          color: #6f6f6f;
          font-size: 11px;
        }
        .cc-host-divider {
          margin: 4px 8px;
          border-top: 1px dashed #2a2a2a;
        }
        .cc-host-empty {
          padding: 8px 12px;
          color: #666;
          font-size: 12px;
        }
        .cc-host-picker::-webkit-scrollbar { display: none; }
        .cc-host-option {
          padding: 5px 12px;
          font-size: 12px;
          color: #aaa;
          cursor: pointer;
          display: flex;
          align-items: center;
          gap: 6px;
          font-family: inherit;
        }
        .cc-host-option:hover { background: #1e1e1e; color: #eee; }
        .cc-host-option.active { color: #f0a500; }
        .cc-host-option.offline { opacity: 0.4; cursor: not-allowed; }
        .cc-host-status { font-size: 8px; color: #444; }
        .cc-host-status.on { color: #3fb950; }
        .cc-input-line {
          display: flex;
          align-items: flex-start;
          gap: 10px;
          padding: 8px 16px 10px;
        }
        .cc-input-line.disabled { opacity: 0.5; }
        .cc-prompt {
          color: #3fb950;
          font-size: 17px;
          line-height: 1.6;
          flex-shrink: 0;
          margin-top: 1px;
          font-family: inherit;
          font-weight: 600;
        }
        .cc-textarea {
          flex: 1;
          background: transparent;
          border: none;
          outline: none;
          color: #f0f0f0;
          font-size: 17px;
          line-height: 1.6;
          resize: none;
          font-family: inherit;
          min-height: 24px;
          max-height: 200px;
          overflow-y: auto;
          scrollbar-width: none;
          caret-color: #3fb950;
        }
        .cc-textarea::-webkit-scrollbar { display: none; }
        .cc-textarea::placeholder { color: #333; }
        .cc-input-spinner {
          color: #f0a500;
          font-size: 14px;
          animation: cc-spin-chars 0.8s steps(8) infinite;
          flex-shrink: 0;
          margin-top: 2px;
        }
        .cc-host-required {
          padding: 0 16px 8px;
          color: #ad7f00;
          font-size: 12px;
        }
        .cc-answer-hint {
          padding: 0 16px 8px;
          color: #7ec8ff;
          font-size: 12px;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        @keyframes cc-spin-chars {
          0%   { content: '⠋'; }
          12%  { content: '⠙'; }
          25%  { content: '⠹'; }
          37%  { content: '⠸'; }
          50%  { content: '⠼'; }
          62%  { content: '⠴'; }
          75%  { content: '⠦'; }
          87%  { content: '⠧'; }
          100% { content: '⠇'; }
        }
      `}</style>
    </div>
  );
}
