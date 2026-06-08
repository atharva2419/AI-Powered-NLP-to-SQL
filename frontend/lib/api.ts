const BASE = "http://localhost:8000";

export interface QueryResult {
  columns: string[];
  rows: unknown[][];
  row_count: number;
  error?: string;
}

export interface QueryResponse {
  sql: string;
  result: QueryResult;
  explanation: string;
  latency_ms: number;
  error?: string;
}

export interface SchemaColumn {
  name: string;
  type: string;
}

export async function fetchExamples(): Promise<string[]> {
  const res = await fetch(`${BASE}/api/examples`);
  if (!res.ok) throw new Error("Failed to fetch examples");
  const data = await res.json();
  return data.examples as string[];
}

export async function fetchSchema(): Promise<SchemaColumn[]> {
  const res = await fetch(`${BASE}/api/schema`);
  if (!res.ok) throw new Error("Failed to fetch schema");
  const data = await res.json();
  return data.columns as SchemaColumn[];
}

export async function runQuery(question: string): Promise<QueryResponse> {
  const res = await fetch(`${BASE}/api/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
  return res.json() as Promise<QueryResponse>;
}
