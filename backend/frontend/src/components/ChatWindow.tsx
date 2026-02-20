"use client";

import { useEffect, useRef } from "react";
import SourcePanel from "./SourcePanel";
import { SourceDocument } from "@/lib/api";

export interface Message {
  id: number;
  role: "user" | "assistant";
  text: string;
  sources?: SourceDocument[];
  error?: boolean;
}

interface Props {
  messages: Message[];
  loading: boolean;
}

export default function ChatWindow({ messages, loading }: Props) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6">
      {messages.length === 0 && (
        <div className="flex h-full items-center justify-center text-gray-400 text-sm">
          Ask a question about your QA documents to get started.
        </div>
      )}

      {messages.map((m) => (
        <div
          key={m.id}
          className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
        >
          <div
            className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              m.role === "user"
                ? "bg-blue-600 text-white rounded-br-sm"
                : m.error
                ? "bg-red-50 border border-red-200 text-red-700 rounded-bl-sm"
                : "bg-white border border-gray-200 text-gray-800 rounded-bl-sm shadow-sm"
            }`}
          >
            <p className="whitespace-pre-wrap">{m.text}</p>
            {m.sources && <SourcePanel sources={m.sources} />}
          </div>
        </div>
      ))}

      {loading && (
        <div className="flex justify-start">
          <div className="bg-white border border-gray-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
            <span className="flex gap-1">
              <span className="h-2 w-2 rounded-full bg-gray-400 animate-bounce [animation-delay:0ms]" />
              <span className="h-2 w-2 rounded-full bg-gray-400 animate-bounce [animation-delay:150ms]" />
              <span className="h-2 w-2 rounded-full bg-gray-400 animate-bounce [animation-delay:300ms]" />
            </span>
          </div>
        </div>
      )}

      <div ref={bottomRef} />
    </div>
  );
}
