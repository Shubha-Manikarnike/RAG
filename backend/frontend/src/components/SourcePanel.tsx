"use client";

import { useState } from "react";
import { SourceDocument } from "@/lib/api";

interface Props {
  sources: SourceDocument[];
}

export default function SourcePanel({ sources }: Props) {
  const [open, setOpen] = useState(false);

  if (sources.length === 0) return null;

  return (
    <div className="mt-3 border-t pt-3">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-xs text-blue-600 hover:underline"
      >
        {open ? "▾" : "▸"} {sources.length} source{sources.length > 1 ? "s" : ""}
      </button>

      {open && (
        <div className="mt-2 space-y-2">
          {sources.map((s, i) => (
            <div
              key={i}
              className="rounded bg-gray-50 border border-gray-200 p-3 text-xs"
            >
              <div className="flex flex-wrap gap-2 mb-1.5">
                {s.metadata.release && (
                  <span className="rounded bg-blue-100 text-blue-700 px-1.5 py-0.5">
                    {s.metadata.release}
                  </span>
                )}
                {s.metadata.doc_type && (
                  <span className="rounded bg-purple-100 text-purple-700 px-1.5 py-0.5">
                    {s.metadata.doc_type}
                  </span>
                )}
                {s.metadata.source && (
                  <span className="text-gray-400">{s.metadata.source}</span>
                )}
              </div>
              <p className="text-gray-600 whitespace-pre-wrap">{s.content}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
