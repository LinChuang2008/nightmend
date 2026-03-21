/**
 * 排障任务清单面板 - OpenCode 暗色风格
 */


export interface Todo {
  id: string;
  text: string;
  status: 'pending' | 'in_progress' | 'done';
}

interface OpsTodoPanelProps {
  todos: Todo[];
}

export default function OpsTodoPanel({ todos }: OpsTodoPanelProps) {
  if (todos.length === 0) return null;
  const doneCount = todos.filter((t) => t.status === 'done').length;

  return (
    <div className="ops-todo-wrap">
      <div className="ops-todo-header">
        <span>排障进度</span>
        <span className="ops-todo-count">{doneCount}/{todos.length}</span>
      </div>
      <div className="ops-todo-list">
        {todos.map((todo) => (
          <div key={todo.id} className={`ops-todo-item ${todo.status}`}>
            <span className="ops-todo-dot" />
            <span className="ops-todo-text">{todo.text}</span>
          </div>
        ))}
      </div>

      <style>{`
        .ops-todo-wrap {
          background: #111;
          border: 1px solid #1e1e1e;
          border-radius: 8px;
          padding: 10px 12px;
          min-width: 180px;
          max-width: 240px;
        }
        .ops-todo-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          font-size: 12px;
          color: #555;
          margin-bottom: 8px;
        }
        .ops-todo-count {
          font-family: monospace;
          color: #444;
        }
        .ops-todo-list {
          display: flex;
          flex-direction: column;
          gap: 5px;
        }
        .ops-todo-item {
          display: flex;
          align-items: center;
          gap: 7px;
          font-size: 12px;
          color: #555;
        }
        .ops-todo-item.in_progress { color: #aaa; }
        .ops-todo-item.done { color: #3a3a3a; text-decoration: line-through; }
        .ops-todo-dot {
          width: 5px;
          height: 5px;
          border-radius: 50%;
          background: #2a2a2a;
          flex-shrink: 0;
        }
        .ops-todo-item.in_progress .ops-todo-dot { background: #4a9eff; }
        .ops-todo-item.done .ops-todo-dot { background: #3fb950; }
        .ops-todo-text {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
      `}</style>
    </div>
  );
}
