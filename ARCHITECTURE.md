# Architecture & End-to-End Flow

## Overview

QA Intelligence is a RAG (Retrieval-Augmented Generation) pipeline that converts Excel-based QA test data into a conversational interface. Users ask natural-language questions and receive accurate, context-backed answers grounded in the actual data.

---

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                          USER'S BROWSER                             │
│                                                                     │
│   ┌─────────────────────────────────────────────────────────────┐  │
│   │               Next.js Frontend  (localhost:3000)            │  │
│   │                                                             │  │
│   │   ┌──────────┐  ┌───────────┐  ┌──────────┐  ┌────────┐  │  │
│   │   │ StatusBar│  │ FilterBar │  │ChatWindow│  │ Source │  │  │
│   │   │(health + │  │(release / │  │(messages │  │ Panel  │  │  │
│   │   │ ingest)  │  │ doc_type) │  │+ typing) │  │(expand)│  │  │
│   │   └──────────┘  └───────────┘  └──────────┘  └────────┘  │  │
│   └─────────────────────────┬───────────────────────────────────┘  │
└─────────────────────────────│───────────────────────────────────────┘
                              │ HTTP (CORS enabled)
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend  (localhost:8000)                 │
│                                                                     │
│   POST /query          GET /health        POST /ingest              │
│        │                                       │                    │
│        ▼                                       ▼                    │
│   ┌─────────────────────────┐      ┌──────────────────────┐        │
│   │   1. Build filter       │      │  Background thread   │        │
│   │      (release/doc_type) │      │  runs ingest.py      │        │
│   │   2. similarity_search  │      └──────────────────────┘        │
│   │      (ChromaDB)         │                                       │
│   │   3. Build context from │      ┌──────────────────────┐        │
│   │      top-k Q&A pairs    │      │  File Watcher        │        │
│   │   4. Call Groq LLM      │      │  (watchdog)          │        │
│   │   5. Return answer +    │      │  Auto-triggers ingest│        │
│   │      sources            │      │  on new .xlsx files  │        │
│   └─────────────────────────┘      └──────────────────────┘        │
│             │                                                        │
│             ▼                                                        │
│   ┌─────────────────────┐    ┌──────────────────────────────────┐  │
│   │  ChromaDB           │    │  Groq LLM                        │  │
│   │  (local vector store│    │  llama-3.3-70b-versatile         │  │
│   │   chroma_db/)       │    │  Synthesises answer from context  │  │
│   │  140 Q&A documents  │    └──────────────────────────────────┘  │
│   └─────────────────────┘                                           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Ingestion Pipeline (One-Time / On Demand)

```
docs/*.xlsx
     │
     ▼
┌────────────────────────────────────────────────────────┐
│                    ingest.py                           │
│                                                        │
│  Pass 1 — Per-file analysis (6 API calls to Groq)     │
│  ┌──────────────────────────────────────────────────┐ │
│  │  For each Excel file:                            │ │
│  │  1. Load into pandas DataFrame                   │ │
│  │  2. Convert to markdown table + compute stats    │ │
│  │  3. Send to Groq (llama-3.3-70b-versatile)       │ │
│  │  4. LLM generates ~20-30 Q&A pairs per file      │ │
│  │  5. Each pair stored as one ChromaDB document    │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  Pass 2 — Cross-release comparison (1 API call)        │
│  ┌──────────────────────────────────────────────────┐ │
│  │  Combined stats from both releases sent to Groq  │ │
│  │  LLM generates comparison Q&A pairs              │ │
│  │  e.g. "Which release had more defects?"          │ │
│  └──────────────────────────────────────────────────┘ │
│                                                        │
│  Embed all Q&A pairs                                   │
│  ┌──────────────────────────────────────────────────┐ │
│  │  sentence-transformers/all-MiniLM-L6-v2 (local)  │ │
│  │  Each "Q: ...\nA: ..." → 384-dim vector          │ │
│  └──────────────────────────────────────────────────┘ │
│            │                                           │
│            ▼                                           │
│       ChromaDB  (backend/chroma_db/)                  │
│       ~140 documents, persisted to disk               │
└────────────────────────────────────────────────────────┘
```

---

## Query Flow (Per User Question)

```
User types: "What are the major defect categories?"
                          │
                          ▼
            Next.js calls POST /query
            { question, release?, doc_type?, k=8 }
                          │
                          ▼
          ┌───────────────────────────────┐
          │  1. Embed the question        │
          │     all-MiniLM-L6-v2 (local) │
          │     → 384-dim query vector   │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────┐
          │  2. Cosine similarity search  │
          │     ChromaDB returns top-8   │
          │     most similar Q&A pairs   │
          │                              │
          │  e.g.                        │
          │  "Q: Which component has the │
          │   most defects?              │
          │   A: Cart (8 issues)..."     │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────┐
          │  3. Build context string      │
          │     Concatenate top-8 Q&A     │
          │     pairs with separators    │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────┐
          │  4. Call Groq LLM             │
          │     System prompt + context  │
          │     + user question          │
          │                              │
          │     LLM synthesises answer   │
          │     from the Q&A context     │
          └───────────────┬───────────────┘
                          │
                          ▼
          ┌───────────────────────────────┐
          │  5. Return to frontend        │
          │  {                           │
          │    answer: "The defect       │
          │     categories are...",      │
          │    sources: [ {content,      │
          │                metadata} ]   │
          │  }                           │
          └───────────────────────────────┘
                          │
                          ▼
            ChatWindow renders answer
            SourcePanel shows expandable
            source Q&A pairs with badges
```

---

## Why Q&A Chunking?

Traditional RAG chunks raw text by character count. This project uses **LLM-generated Q&A pairs** as chunks instead.

| Approach | How it's stored | Why it works |
|---|---|---|
| Raw row chunking | `"Issue Key: RA-101\nSeverity: Sev4\n..."` | Poor — flat key-value text doesn't embed well for natural language queries |
| Q&A chunking (this project) | `"Q: Which component has the most defects?\nA: Cart (8 issues)"` | Great — user queries match semantically to stored questions |

When a user asks *"What are the major defect categories?"*, cosine similarity against stored `Q:` lines is naturally high because both are natural-language questions about the same topic.

---

## Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Frontend | Next.js 14, TypeScript, Tailwind CSS | Chat UI |
| API | FastAPI, Uvicorn | REST endpoints |
| Orchestration | LangChain, LangChain-Community | RAG pipeline |
| Vector Store | ChromaDB | Local semantic search |
| Embeddings | sentence-transformers `all-MiniLM-L6-v2` | Local, no API needed |
| Ingest LLM | Groq `llama-3.3-70b-versatile` | Q&A pair generation (free tier) |
| Query LLM | Groq `llama-3.3-70b-versatile` | Answer synthesis |
| Data | pandas, openpyxl | Excel ingestion |
| File watching | watchdog | Auto-ingest on new docs |

---

## Data Flow Summary

```
Excel files → Groq LLM → Q&A pairs → Embeddings → ChromaDB
                                                        │
User question → Embed → Similarity search → Top-k Q&A ─┘
                                                        │
                                              Groq LLM synthesises
                                                        │
                                              Answer + sources → UI
```
