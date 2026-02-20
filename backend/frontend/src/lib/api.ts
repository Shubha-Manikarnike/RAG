const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface SourceDocument {
  content: string;
  metadata: Record<string, string>;
}

export interface QueryResponse {
  answer: string;
  sources: SourceDocument[];
}

export interface HealthResponse {
  status: string;
  chroma_ready: boolean;
  total_docs: number;
  ingest_running: boolean;
  llm_model: string;
}

export interface QueryRequest {
  question: string;
  release?: string;
  doc_type?: string;
  k?: number;
}

export async function queryRAG(payload: QueryRequest): Promise<QueryResponse> {
  const res = await fetch(`${API_BASE}/query`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Request failed: ${res.status}`);
  }
  return res.json();
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
  if (!res.ok) throw new Error("Backend unreachable");
  return res.json();
}

export async function triggerIngest(): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/ingest`, { method: "POST" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail ?? `Ingest failed: ${res.status}`);
  }
  return res.json();
}
