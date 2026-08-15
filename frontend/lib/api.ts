// Trailing slashes are stripped because every call below appends "/api/...".
// A base of "https://host/" would produce "https://host//api/query", and
// Starlette matches routes exactly — a doubled slash is a 404, not a redirect.
// Pasting a URL with the trailing slash the browser shows is an easy mistake,
// and not one worth debugging twice.
const BASE = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/+$/, "");

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  /** true when the database capped the result set at MAX_RESULT_ROWS */
  truncated?: boolean;
  error?: string;
}

export interface QueryResponse {
  sql: string;
  result: QueryResult;
  explanation: string;
  latency_ms: number;
  /** served from the response cache without calling the LLM */
  cached?: boolean;
  /** how many generation attempts it took; >1 means the model self-corrected */
  attempts?: number;
  error?: string;
  /** the demo's rate limit rejected this request (HTTP 429) */
  rateLimited?: boolean;
}

export interface SchemaColumn {
  name: string;
  type: string;
}

export interface HistoryItem {
  id: number;
  question: string;
  sql: string;
  result: QueryResult;
  explanation: string;
  latency_ms: number;
  created_at: string;
}

export async function fetchExamples(): Promise<string[]> {
  const res = await fetch(`${BASE}/api/examples`);
  if (!res.ok) throw new Error("Failed to fetch examples");
  const data = await res.json();
  return data.examples as string[];
}

export interface Schema {
  columns: SchemaColumn[];
  /** rows actually loaded — the hosted demo runs a sample, not the full year */
  rowCount: number;
}

export async function fetchSchema(): Promise<Schema> {
  const res = await fetch(`${BASE}/api/schema`);
  if (!res.ok) throw new Error("Failed to fetch schema");
  const data = await res.json();
  return {
    columns: data.columns as SchemaColumn[],
    rowCount: (data.row_count as number) ?? 0,
  };
}

export async function runQuery(question: string): Promise<QueryResponse> {
  const res = await fetch(`${BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  const data = (await res.json()) as QueryResponse;
  // A throttled request is not a failed translation — the UI phrases the two
  // very differently, so the distinction has to survive the fetch.
  if (res.status === 429) return { ...data, rateLimited: true };
  return data;
}

export async function fetchHistory(): Promise<HistoryItem[]> {
  const res = await fetch(`${BASE}/api/history`);
  if (!res.ok) throw new Error("Failed to fetch history");
  const data = await res.json();
  return data.history as HistoryItem[];
}
