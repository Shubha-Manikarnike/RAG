"use client";

import { useState } from "react";
import ChatWindow, { Message } from "@/components/ChatWindow";
import FilterBar from "@/components/FilterBar";
import StatusBar from "@/components/StatusBar";
import { queryRAG } from "@/lib/api";

export default function Home() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({
    release: "All releases",
    docType: "All types",
    k: 8,
  });

  const handleFilterChange = (field: string, value: string | number) => {
    setFilters((f) => ({ ...f, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const question = input.trim();
    if (!question || loading) return;

    const userMsg: Message = { id: Date.now(), role: "user", text: question };
    setMessages((m) => [...m, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const payload = {
        question,
        release: filters.release === "All releases" ? undefined : filters.release,
        doc_type: filters.docType === "All types" ? undefined : filters.docType,
        k: filters.k,
      };

      const data = await queryRAG(payload);

      setMessages((m) => [
        ...m,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: data.answer,
          sources: data.sources,
        },
      ]);
    } catch (err: unknown) {
      setMessages((m) => [
        ...m,
        {
          id: Date.now() + 1,
          role: "assistant",
          text: err instanceof Error ? err.message : "Something went wrong.",
          error: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e as unknown as React.FormEvent);
    }
  };

  return (
    <div className="flex flex-col h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b px-6 py-4 shrink-0">
        <div className="max-w-4xl mx-auto space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-lg font-semibold text-gray-900">QA Intelligence</h1>
              <p className="text-xs text-gray-500">
                Ask questions about your test executions, defects, and release data
              </p>
            </div>
            <button
              onClick={() => setMessages([])}
              className="text-xs text-gray-400 hover:text-gray-600"
            >
              Clear chat
            </button>
          </div>
          <StatusBar />
          <FilterBar
            release={filters.release}
            docType={filters.docType}
            k={filters.k}
            onChange={handleFilterChange}
          />
        </div>
      </header>

      {/* Chat */}
      <main className="flex-1 overflow-hidden max-w-4xl w-full mx-auto flex flex-col">
        <ChatWindow messages={messages} loading={loading} />

        {/* Input */}
        <form onSubmit={handleSubmit} className="shrink-0 px-4 pb-6 pt-2">
          <div className="flex items-end gap-2 rounded-2xl border border-gray-300 bg-white px-4 py-3 shadow-sm focus-within:ring-2 focus-within:ring-blue-500">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask about defects, test results, release comparisons… (Enter to send)"
              rows={1}
              className="flex-1 resize-none text-sm text-gray-800 placeholder-gray-400 focus:outline-none max-h-40 leading-relaxed"
              onInput={(e) => {
                const t = e.currentTarget;
                t.style.height = "auto";
                t.style.height = t.scrollHeight + "px";
              }}
            />
            <button
              type="submit"
              disabled={!input.trim() || loading}
              className="shrink-0 rounded-xl bg-blue-600 px-4 py-2 text-sm text-white font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              Send
            </button>
          </div>
          <p className="mt-1.5 text-center text-xs text-gray-400">
            Shift+Enter for new line · Enter to send
          </p>
        </form>
      </main>
    </div>
  );
}
