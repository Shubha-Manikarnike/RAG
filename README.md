# QA Intelligence — RAG Pipeline

A Retrieval-Augmented Generation (RAG) system that lets you ask natural-language questions about QA test data stored in Excel files. Built with FastAPI, LangChain, ChromaDB, and Next.js.

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.10+ |
| Node.js | 18+ |
| npm | 9+ |

---

## Project Structure

```
Roopa's documents/
├── docs/                          # Excel source documents
│   ├── ReleaseA_Defects.xlsx
│   ├── ReleaseA_TestExecution.xlsx
│   ├── ReleaseA_MetaData.xlsx
│   ├── ReleaseB_Defects.xlsx
│   ├── ReleaseB_TestExecution.xlsx
│   └── ReleaseB_Metadata.xlsx
├── backend/                       # FastAPI + RAG pipeline
│   ├── ingest.py                  # LLM-driven document ingestion
│   ├── main.py                    # API server
│   ├── debug_query.py             # Retrieval debugger
│   ├── requirements.txt
│   └── .env                       # API keys (not committed)
├── frontend/                      # Next.js chat UI
│   ├── src/
│   │   ├── app/page.tsx           # Main chat page
│   │   ├── components/            # ChatWindow, FilterBar, StatusBar, SourcePanel
│   │   └── lib/api.ts             # Typed API client
│   └── .env.local
└── project/                       # Documentation
    ├── README.md
    └── ARCHITECTURE.md
```

---

## Setup

### 1. Backend

```bash
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create `backend/.env`:
```
GROQ_API_KEY=gsk_...
ANTHROPIC_API_KEY=sk-ant-...   # optional, for future use
```

Ingest documents into ChromaDB:
```bash
python ingest.py
```

Start the API server:
```bash
uvicorn main:app --reload
```

API is available at `http://localhost:8000`
Interactive docs at `http://localhost:8000/docs`

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

UI is available at `http://localhost:3000`

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Backend status, doc count, ingest state |
| `POST` | `/query` | Ask a question, get an answer + sources |
| `POST` | `/ingest` | Manually trigger re-ingestion |
| `GET` | `/debug?q=...` | Inspect raw retrieval results |

### Query request body
```json
{
  "question": "What are the major defect categories?",
  "release": "ReleaseA",
  "doc_type": "defect",
  "k": 8
}
```
`release` and `doc_type` are optional filters.

---

## Adding New Documents

Drop any `.xlsx` file into the `docs/` folder following the naming convention:

```
<ReleaseName>_Defects.xlsx
<ReleaseName>_TestExecution.xlsx
<ReleaseName>_Metadata.xlsx
```

The file watcher detects the change and re-ingests automatically. Alternatively, click **Re-ingest docs** in the UI or call `POST /ingest`.

---

## Debugging Retrieval

```bash
python debug_query.py "What are the major defect categories?"
python debug_query.py "Which tests failed?" --release ReleaseB --doc_type test_execution
```

---

## Transferring to Another Machine

Zip everything **except**:
- `backend/venv/`
- `backend/chroma_db/`
- `frontend/node_modules/`
- `frontend/.next/`

On the new machine, follow the Setup steps above. The recipient will need their own `backend/.env` with API keys.
