'use client';

import { useEffect, useState } from 'react';
import { Light as SyntaxHighlighter } from 'react-syntax-highlighter';
import sql from 'react-syntax-highlighter/dist/esm/languages/hljs/sql';
import { atomOneDark } from 'react-syntax-highlighter/dist/esm/styles/hljs';
import {
  fetchExamples,
  fetchSchema,
  fetchHistory,
  runQuery,
  type HistoryItem,
  type QueryResponse,
  type SchemaColumn,
} from '@/lib/api';
import ResultChart from '@/components/ResultChart';
import { GLOSSARY } from '@/lib/glossary';
import { decodeValue, formatColumnName, formatValue } from '@/lib/format';

SyntaxHighlighter.registerLanguage('sql', sql);

const FRIENDLY_ERROR =
  "I couldn't generate a valid query for that. Try rephrasing — for example, 'What is the average fare?'";

// The full 2024 dataset is ~41M rows. A hosted free-tier instance loads a
// sample instead, so anything well under the full year is labelled as such —
// claiming 41M rows on a demo backed by 1M would be a lie the reader cannot
// check.
const FULL_YEAR_ROWS = 30_000_000;

function isSampled(rowCount: number): boolean {
  return rowCount > 0 && rowCount < FULL_YEAR_ROWS;
}

function formatRowCount(rowCount: number): string {
  if (rowCount >= 1_000_000) return `${(rowCount / 1_000_000).toFixed(1)}M`;
  if (rowCount >= 1_000) return `${Math.round(rowCount / 1_000)}k`;
  return String(rowCount);
}

function timeAgo(isoString: string): string {
  const diff = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export default function Home() {
  const [question, setQuestion] = useState('');
  const [examples, setExamples] = useState<string[]>([]);
  const [schema, setSchema] = useState<SchemaColumn[]>([]);
  const [rowCount, setRowCount] = useState(0);
  const [schemaOpen, setSchemaOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [networkError, setNetworkError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [history, setHistory] = useState<HistoryItem[]>([]);

  useEffect(() => {
    fetchExamples().then(setExamples).catch(() => {});
    fetchSchema()
      .then((s) => {
        setSchema(s.columns);
        setRowCount(s.rowCount);
      })
      .catch(() => {});
    fetchHistory().then(setHistory).catch(() => {});
  }, []);

  const submit = async (q: string) => {
    if (!q.trim()) return;
    setLoading(true);
    setResult(null);
    setNetworkError(null);
    try {
      const data = await runQuery(q.trim());
      setResult(data);
      if (!data.error && !data.result?.error) {
        fetchHistory().then(setHistory).catch(() => {});
      }
    } catch {
      setNetworkError('Could not reach the server. Is the backend running on port 8000?');
    } finally {
      setLoading(false);
    }
  };

  const handleChip = (ex: string) => {
    setQuestion(ex);
    submit(ex);
  };

  const handleCopy = () => {
    if (!result?.sql) return;
    navigator.clipboard.writeText(result.sql);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleHistoryClick = (item: HistoryItem) => {
    setQuestion(item.question);
    setResult({
      sql: item.sql,
      result: item.result,
      explanation: item.explanation,
      latency_ms: item.latency_ms,
    });
    setNetworkError(null);
  };

  const displayRows = result?.result?.rows?.slice(0, 10) ?? [];
  const apiError = result?.error ?? result?.result?.error ?? null;

  return (
    <div className="min-h-screen bg-zinc-50 py-16 px-4">
      <div className="mx-auto w-full max-w-[780px]">

        {/* Header */}
        <div className="mb-10 flex items-center gap-3">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-amber-400 text-xl shadow-sm">
            🚕
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900">
              NYC Taxi Explorer
            </h1>
            <p className="mt-0.5 text-sm text-zinc-500">
              Ask questions about {rowCount > 0 ? formatRowCount(rowCount) : '40M+'} taxi
              trips from 2024 in plain English.
              {isSampled(rowCount) && (
                <span
                  title="The hosted demo loads a month-stratified sample so it fits a free-tier host. Run it locally for the full year."
                  className="ml-1.5 rounded bg-zinc-200 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-zinc-600"
                >
                  sample
                </span>
              )}
            </p>
          </div>
        </div>

        {/* Search input */}
        <div className="flex gap-2 mb-4">
          <input
            type="text"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit(question)}
            placeholder="e.g. What is the average fare amount?"
            className="flex-1 rounded-lg border border-zinc-200 bg-white px-4 py-3 text-sm text-zinc-900 placeholder:text-zinc-400 shadow-sm focus:outline-none focus:ring-2 focus:ring-amber-400 focus:border-transparent"
          />
          <button
            onClick={() => submit(question)}
            disabled={loading || !question.trim()}
            className="rounded-lg bg-zinc-900 px-5 py-3 text-sm font-medium text-white transition-colors hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {loading ? 'Asking…' : 'Ask'}
          </button>
        </div>

        {/* Example chips + schema toggle */}
        <div className="flex flex-wrap items-center justify-between gap-y-3 mb-6">
          <div className="flex flex-wrap gap-2">
            {examples.map((ex) => (
              <button
                key={ex}
                onClick={() => handleChip(ex)}
                className="rounded-full border border-zinc-200 bg-white px-3 py-1.5 text-xs text-zinc-600 transition-colors hover:border-zinc-400 hover:text-zinc-900"
              >
                {ex}
              </button>
            ))}
          </div>
          {schema.length > 0 && (
            <button
              onClick={() => setSchemaOpen((o) => !o)}
              className="flex items-center gap-1.5 text-xs text-zinc-500 hover:text-zinc-800 transition-colors shrink-0"
            >
              <span>{schemaOpen ? '▴' : '▾'}</span>
              <span>Glossary</span>
            </button>
          )}
        </div>

        {/* Collapsible glossary panel */}
        {schemaOpen && schema.length > 0 && (
          <div className="mb-8 overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm">
            <div className="flex items-baseline justify-between border-b border-zinc-100 px-4 py-2.5">
              <span className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
                taxi — {schema.length} columns
              </span>
              <span className="text-xs text-zinc-400">
                everything you can ask about
              </span>
            </div>
            <div className="divide-y divide-zinc-50">
              {schema.map(({ name, type }) => (
                <div key={name} className="flex flex-col gap-0.5 px-4 py-2 sm:flex-row sm:items-baseline sm:gap-3">
                  <span className="w-52 shrink-0 font-mono text-xs font-medium text-zinc-800">
                    {name}
                    <span className="ml-2 font-sans text-[10px] uppercase text-zinc-400">{type}</span>
                  </span>
                  <span className="text-xs leading-relaxed text-zinc-500">
                    {GLOSSARY[name] ?? ''}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="space-y-4 animate-pulse">
            <div className="h-28 rounded-lg bg-zinc-200" />
            <div className="h-48 rounded-lg bg-zinc-200" />
            <div className="h-14 rounded-lg bg-zinc-200" />
          </div>
        )}

        {/* Network error */}
        {!loading && networkError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {networkError}
          </div>
        )}

        {/* Results */}
        {!loading && result && (
          <div className="space-y-6">

            {/* Throttled by the demo's budget — not a translation failure */}
            {apiError && result.rateLimited && (
              <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3">
                <p className="text-sm text-sky-800">{apiError}</p>
              </div>
            )}

            {/* Friendly API/query error */}
            {apiError && !result.rateLimited && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
                <p className="text-sm text-amber-800">{FRIENDLY_ERROR}</p>
                <p className="mt-1 font-mono text-xs text-amber-600">{apiError}</p>
              </div>
            )}

            {!apiError && (
              <>
                {/* SQL block */}
                <div className="overflow-hidden rounded-lg border border-zinc-200 shadow-sm">
                  <div className="flex items-center justify-between border-b border-zinc-700 bg-[#282c34] px-4 py-2">
                    <span className="text-xs font-semibold tracking-widest text-zinc-400 uppercase">
                      SQL
                    </span>
                    <button
                      onClick={handleCopy}
                      className="text-xs text-zinc-400 hover:text-zinc-100 transition-colors"
                    >
                      {copied ? '✓ Copied' : 'Copy'}
                    </button>
                  </div>
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
                    {result.sql}
                  </SyntaxHighlighter>
                </div>

                {/* Auto-detected chart (stat card / bar / line) */}
                <ResultChart columns={result.result.columns} rows={result.result.rows} />

                {/* Result table */}
                <div className="overflow-hidden rounded-lg border border-zinc-200 shadow-sm">
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-zinc-200 bg-zinc-50">
                          {result.result.columns.map((col) => (
                            <th
                              key={col}
                              title={GLOSSARY[col] ?? col}
                              className="px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-zinc-500 whitespace-nowrap"
                            >
                              {formatColumnName(col)}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-zinc-100 bg-white">
                        {displayRows.map((row, i) => (
                          <tr key={i} className="hover:bg-zinc-50 transition-colors">
                            {(row as unknown[]).map((cell, j) => {
                              const col = result.result.columns[j];
                              const decoded = decodeValue(col, cell);
                              return (
                                <td
                                  key={j}
                                  // Decoded codes keep the raw value in the
                                  // tooltip — someone writing their own SQL
                                  // still needs to know it was a 1.
                                  title={decoded ? `${col} = ${String(cell)}` : undefined}
                                  className="px-4 py-2.5 font-mono text-xs text-zinc-700 whitespace-nowrap"
                                >
                                  {cell === null || cell === undefined ? (
                                    <span className="text-zinc-400">null</span>
                                  ) : (
                                    formatValue(col, cell)
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {(result.result.row_count > 10 || result.result.truncated) && (
                    <div className="border-t border-zinc-100 bg-zinc-50 px-4 py-2 text-xs text-zinc-400">
                      Showing 10 of {result.result.row_count.toLocaleString()} rows
                      {result.result.truncated && ' (result capped by the server)'}
                    </div>
                  )}
                </div>

                {/* Explanation */}
                <div className="border-l-4 border-zinc-300 pl-4">
                  <p className="text-base leading-relaxed text-zinc-700">
                    {result.explanation}
                  </p>
                </div>

                {/* Latency + how the answer was produced */}
                <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
                  <span>Answered in {(result.latency_ms / 1000).toFixed(1)}s</span>
                  {result.cached && (
                    <span
                      title="Served from cache — no LLM call was made"
                      className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700"
                    >
                      cached
                    </span>
                  )}
                  {(result.attempts ?? 1) > 1 && (
                    <span
                      title="The first query failed; the model was shown the database error and corrected itself"
                      className="rounded-full bg-violet-50 px-2 py-0.5 font-medium text-violet-700"
                    >
                      self-corrected ({result.attempts} attempts)
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        )}

        {/* Recent queries */}
        {history.length > 0 && (
          <div className="mt-12">
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-widest text-zinc-400">
              Recent queries
            </h2>
            <div className="space-y-1">
              {history.map((item) => (
                <button
                  key={item.id}
                  onClick={() => handleHistoryClick(item)}
                  className="w-full rounded-lg border border-zinc-100 bg-white px-4 py-3 text-left transition-colors hover:border-zinc-300 hover:bg-zinc-50"
                >
                  <div className="flex items-start justify-between gap-4">
                    <span className="text-sm text-zinc-700 line-clamp-1">{item.question}</span>
                    <span className="shrink-0 text-xs text-zinc-400">{timeAgo(item.created_at)}</span>
                  </div>
                  <p className="mt-0.5 font-mono text-xs text-zinc-400 line-clamp-1">{item.sql}</p>
                </button>
              ))}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
