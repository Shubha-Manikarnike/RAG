"use client";

import { useEffect, useState } from "react";
import { fetchHealth, triggerIngest, HealthResponse } from "@/lib/api";

export default function StatusBar() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);
  const [ingesting, setIngesting] = useState(false);

  const load = async () => {
    try {
      const h = await fetchHealth();
      setHealth(h);
      setError(false);
    } catch {
      setError(true);
    }
  };

  useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  const handleIngest = async () => {
    try {
      setIngesting(true);
      await triggerIngest();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Ingest failed");
    } finally {
      setIngesting(false);
      setTimeout(load, 1000);
    }
  };

  if (error) {
    return (
      <div className="flex items-center gap-2 text-sm text-red-500">
        <span className="h-2 w-2 rounded-full bg-red-500" />
        Backend unreachable
      </div>
    );
  }

  if (!health) return null;

  return (
    <div className="flex flex-wrap items-center gap-4 text-sm text-gray-500">
      <span className="flex items-center gap-1.5">
        <span
          className={`h-2 w-2 rounded-full ${
            health.chroma_ready ? "bg-green-500" : "bg-yellow-400"
          }`}
        />
        {health.total_docs} docs indexed
      </span>
      <span>Model: {health.llm_model}</span>
      {health.ingest_running && (
        <span className="text-yellow-500 animate-pulse">Ingesting…</span>
      )}
      <button
        onClick={handleIngest}
        disabled={ingesting || health.ingest_running}
        className="ml-auto rounded border border-gray-300 px-3 py-1 text-xs hover:bg-gray-100 disabled:opacity-40"
      >
        {ingesting || health.ingest_running ? "Ingesting…" : "Re-ingest docs"}
      </button>
    </div>
  );
}
