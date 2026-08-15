'use client';

import { useEffect, useRef, useState } from 'react';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import sql from 'react-syntax-highlighter/dist/esm/languages/hljs/sql';
import { atomOneDark } from 'react-syntax-highlighter/dist/esm/styles/hljs';

SyntaxHighlighter.registerLanguage('sql', sql);

/**
 * The generated SQL, and a way to change it.
 *
 * Read-only SQL is a receipt; editable SQL is a tool. Someone learning gets to
 * ask "what if I group by hour instead?" and find out in a few hundred
 * milliseconds, without spending an LLM call or knowing how to run DuckDB.
 *
 * Highlighted by default and a plain textarea while editing: the highlighter
 * renders styled spans, not editable text, and layering a transparent
 * textarea over it to fake both at once is a well-known source of alignment
 * bugs (fonts, tabs, wrapping, mobile carets). A visible mode switch is worth
 * more than the syntax colours are during the few seconds of typing.
 */
export default function SqlEditor({
  value,
  onRun,
  running,
  edited,
  error,
}: {
  value: string;
  onRun: (sql: string) => void;
  running: boolean;
  edited: boolean;
  error: string | null;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  const [copied, setCopied] = useState(false);
  const [lastValue, setLastValue] = useState(value);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // A new query arrived, so any in-progress edit of the previous one is stale.
  // Adjusted during render rather than in an effect: React re-runs this pass
  // before touching the DOM, so there is no flash of the old SQL and no
  // cascading second render. (https://react.dev/learn/you-might-not-need-an-effect)
  if (value !== lastValue) {
    setLastValue(value);
    setDraft(value);
    setEditing(false);
  }

  useEffect(() => {
    if (editing) textareaRef.current?.focus();
  }, [editing]);

  const handleCopy = () => {
    navigator.clipboard?.writeText(draft);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const run = () => {
    const trimmed = draft.trim();
    if (trimmed) onRun(trimmed);
  };

  // Ctrl/Cmd+Enter runs, matching every SQL console people have used.
  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      run();
    }
    if (e.key === 'Escape') {
      setDraft(value);
      setEditing(false);
    }
  };

  const lineCount = Math.max(3, draft.split('\n').length);

  return (
    <div className="overflow-hidden rounded-lg border border-zinc-200 shadow-sm">
      <div className="flex items-center justify-between border-b border-zinc-700 bg-[#282c34] px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
            SQL
          </span>
          {edited && (
            <span
              title="You changed this query — the results below come from your version, not the generated one"
              className="rounded-full bg-amber-400/20 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-amber-300"
            >
              edited
            </span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {editing ? (
            <>
              <button
                onClick={() => {
                  setDraft(value);
                  setEditing(false);
                }}
                className="text-xs text-zinc-400 transition-colors hover:text-zinc-100"
              >
                Cancel
              </button>
              <button
                onClick={run}
                disabled={running || !draft.trim()}
                className="rounded bg-amber-400 px-2.5 py-1 text-xs font-medium text-zinc-900 transition-colors hover:bg-amber-300 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {running ? 'Running…' : 'Run ⌘↵'}
              </button>
            </>
          ) : (
            <>
              <button
                onClick={() => setEditing(true)}
                className="text-xs text-zinc-400 transition-colors hover:text-zinc-100"
              >
                Edit
              </button>
              <button
                onClick={handleCopy}
                className="text-xs text-zinc-400 transition-colors hover:text-zinc-100"
              >
                {copied ? '✓ Copied' : 'Copy'}
              </button>
            </>
          )}
        </div>
      </div>

      {editing ? (
        <textarea
          ref={textareaRef}
          aria-label="Edit SQL query"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={handleKeyDown}
          spellCheck={false}
          rows={lineCount}
          className="w-full resize-y bg-[#282c34] px-4 py-4 font-mono text-[13px] leading-relaxed text-zinc-100 outline-none focus:ring-1 focus:ring-inset focus:ring-amber-400"
        />
      ) : (
        <SyntaxHighlighter
          language="sql"
          style={atomOneDark}
          customStyle={{
            margin: 0,
            borderRadius: 0,
            fontSize: '13px',
            padding: '16px',
            lineHeight: '1.6',
          }}
        >
          {draft}
        </SyntaxHighlighter>
      )}

      {error && (
        <div className="border-t border-red-900/40 bg-red-950/40 px-4 py-2.5">
          <p className="font-mono text-xs leading-relaxed text-red-300">{error}</p>
        </div>
      )}
    </div>
  );
}
