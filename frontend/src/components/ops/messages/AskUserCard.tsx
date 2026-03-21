/**
 * AI 提问 - Claude Code 风格：终端内联问答
 */
import { useState } from 'react';

interface AskUserCardProps {
  messageId: string;
  question: string;
  inputType: 'radio' | 'checkbox' | 'text';
  options?: string[];
  status: 'pending' | 'answered';
  answer?: string;
  onAnswer: (messageId: string, answer: string) => void;
}

export default function AskUserCard({ messageId, question, inputType, options = [], status, answer, onAnswer }: AskUserCardProps) {
  const [radioValue, setRadioValue] = useState('');
  const [checkValues, setCheckValues] = useState<string[]>([]);
  const [textValue, setTextValue] = useState('');

  const handleSubmit = () => {
    let ans = '';
    if (inputType === 'radio') ans = radioValue;
    else if (inputType === 'checkbox') ans = checkValues.join(', ');
    else ans = textValue;
    if (ans) onAnswer(messageId, ans);
  };

  const isAnswered = status === 'answered';

  return (
    <div className="cc-ask-wrap">
      <div className="cc-ask-q">
        <span className="cc-ask-mark">?</span>
        <span>{question}</span>
      </div>

      {isAnswered ? (
        <div className="cc-ask-answered">
          <span className="cc-ask-arrow">&gt;</span>
          <span>{answer}</span>
        </div>
      ) : (
        <div className="cc-ask-body">
          {inputType === 'radio' && options.map((opt, i) => (
            <label key={opt} className="cc-ask-option">
              <input type="radio" name={messageId} value={opt} checked={radioValue === opt} onChange={() => setRadioValue(opt)} />
              <span>{i + 1}. {opt}</span>
            </label>
          ))}
          {inputType === 'checkbox' && options.map((opt) => (
            <label key={opt} className="cc-ask-option">
              <input
                type="checkbox"
                value={opt}
                checked={checkValues.includes(opt)}
                onChange={(e) => {
                  if (e.target.checked) setCheckValues([...checkValues, opt]);
                  else setCheckValues(checkValues.filter((v) => v !== opt));
                }}
              />
              <span>{opt}</span>
            </label>
          ))}
          {inputType === 'text' && (
            <div className="cc-ask-text-row">
              <span className="cc-ask-arrow">&gt;</span>
              <input
                className="cc-ask-input"
                value={textValue}
                onChange={(e) => setTextValue(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSubmit(); }}
                placeholder="type answer..."
                autoFocus
              />
            </div>
          )}
          <button className="cc-ask-submit" onClick={handleSubmit}>[enter]</button>
        </div>
      )}

      <style>{`
        .cc-ask-wrap {
          padding: 4px 0;
          font-family: 'SF Mono', 'Fira Code', monospace;
        }
        .cc-ask-q {
          display: flex;
          gap: 10px;
          padding: 2px 16px;
          font-size: 14px;
          color: #d0d0d0;
          align-items: baseline;
        }
        .cc-ask-mark {
          color: #f0a500;
          flex-shrink: 0;
        }
        .cc-ask-answered {
          display: flex;
          gap: 10px;
          padding: 2px 16px;
          font-size: 13px;
          color: #888;
        }
        .cc-ask-arrow { color: #888; flex-shrink: 0; }
        .cc-ask-body {
          padding: 4px 16px 4px 28px;
          display: flex;
          flex-direction: column;
          gap: 4px;
        }
        .cc-ask-option {
          display: flex;
          align-items: center;
          gap: 8px;
          font-size: 13px;
          color: #aaa;
          cursor: pointer;
          font-family: inherit;
        }
        .cc-ask-option input { accent-color: #f0a500; }
        .cc-ask-text-row {
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .cc-ask-input {
          background: transparent;
          border: none;
          border-bottom: 1px solid #333;
          outline: none;
          color: #e0e0e0;
          font-size: 13px;
          font-family: inherit;
          padding: 2px 4px;
          caret-color: #f0a500;
          flex: 1;
        }
        .cc-ask-submit {
          background: transparent;
          border: none;
          color: #f0a500;
          font-size: 12px;
          font-family: inherit;
          cursor: pointer;
          padding: 3px 0;
          margin-top: 4px;
          align-self: flex-start;
        }
        .cc-ask-submit:hover { color: #ffb800; }
      `}</style>
    </div>
  );
}
