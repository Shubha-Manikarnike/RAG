"""
main.py - FastAPI RAG query API over QA Excel documents.

Environment variables (put in backend/.env):
    GROQ_API_KEY       required for query answering
    ANTHROPIC_API_KEY  reserved for when Anthropic credits are available

Run:
    uvicorn main:app --reload

New document ingestion
----------------------
Drop any .xlsx file into the docs/ folder — the file watcher detects the
change and re-ingests automatically.  Or call POST /ingest to trigger manually.
"""

import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from langchain_groq import ChatGroq
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from ingest import ingest, DOCS_DIR, CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

LLM_MODEL = "llama-3.3-70b-versatile"

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

vectorstore: Chroma | None = None
embeddings: HuggingFaceEmbeddings | None = None
llm: ChatGroq | None = None

# Ensures only one ingestion runs at a time
_ingest_lock = threading.Lock()
_ingest_running = False
_executor = ThreadPoolExecutor(max_workers=1)


# ---------------------------------------------------------------------------
# Background ingestion
# ---------------------------------------------------------------------------

def _reload_vectorstore():
    """Re-open ChromaDB after ingestion so the running server picks up new docs."""
    global vectorstore
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    print(f"Vectorstore reloaded — {vectorstore._collection.count()} docs.")


def _run_ingest():
    """Run full ingestion pipeline in a background thread."""
    global _ingest_running
    if not _ingest_lock.acquire(blocking=False):
        print("[ingest] Already in progress — skipping.")
        return
    _ingest_running = True
    try:
        print("[ingest] Starting ingestion ...")
        ingest()
        _reload_vectorstore()
        print("[ingest] Done.")
    except Exception as exc:
        print(f"[ingest] Failed: {exc}")
    finally:
        _ingest_running = False
        _ingest_lock.release()


# ---------------------------------------------------------------------------
# File watcher — auto-ingest when docs/ changes
# ---------------------------------------------------------------------------

class DocsChangeHandler(FileSystemEventHandler):
    """Trigger re-ingestion whenever an Excel file is added or modified."""

    def _handle(self, event):
        if not event.is_directory and str(event.src_path).endswith(".xlsx"):
            print(f"[watcher] Detected change: {event.src_path} — queuing ingestion.")
            _executor.submit(_run_ingest)

    def on_created(self, event):
        self._handle(event)

    def on_modified(self, event):
        self._handle(event)


# ---------------------------------------------------------------------------
# Lifespan — startup / shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global vectorstore, embeddings, llm

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not set. Add it to backend/.env")

    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    if not CHROMA_DIR.exists():
        print("ChromaDB not found — running initial ingestion ...")
        ingest()

    print(f"Connecting to ChromaDB at: {CHROMA_DIR.resolve()}")
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )
    print(f"Loaded {vectorstore._collection.count()} documents.")

    llm = ChatGroq(model=LLM_MODEL, api_key=api_key)

    # Start watching docs/ for new/changed files
    observer = Observer()
    observer.schedule(DocsChangeHandler(), str(DOCS_DIR), recursive=False)
    observer.start()
    print(f"Watching {DOCS_DIR} for new documents ...")

    print("API ready.")
    yield

    observer.stop()
    observer.join()
    vectorstore = None
    llm = None


app = FastAPI(title="QA RAG API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

PROMPT = ChatPromptTemplate.from_messages([
    (
        "system",
        """You are a QA analyst assistant helping users understand test management data \
across software releases.

The context below contains Q&A pairs pre-generated from the actual data. \
Use them to synthesise a helpful, accurate answer. The user's question may be \
phrased differently from the stored questions — use your judgement to find and \
combine relevant information across all the provided pairs.

Rules:
- Always try to give a useful answer by combining related Q&A pairs from the context.
- If multiple Q&A pairs are relevant, synthesise them into one coherent response.
- If the context genuinely contains no relevant information, say so briefly.
- Do not say "cannot be determined" when the context clearly contains related facts.

Context:
{context}""",
    ),
    ("human", "{question}"),
])

# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    question: str
    release: str | None = None   # "ReleaseA" | "ReleaseB"
    doc_type: str | None = None  # "defect" | "test_execution" | "metadata" | "comparison"
    k: int = 8


class SourceDocument(BaseModel):
    content: str
    metadata: dict


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceDocument]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Liveness check."""
    return {
        "status": "ok",
        "chroma_ready": vectorstore is not None,
        "total_docs": vectorstore._collection.count() if vectorstore else 0,
        "ingest_running": _ingest_running,
        "llm_model": LLM_MODEL,
    }


@app.post("/ingest")
async def trigger_ingest(background_tasks: BackgroundTasks):
    """
    Manually trigger re-ingestion of all documents in the docs/ folder.
    Returns immediately; ingestion runs in the background.
    """
    if _ingest_running:
        raise HTTPException(status_code=409, detail="Ingestion already in progress.")
    background_tasks.add_task(_run_ingest)
    return {"status": "ingestion started — call GET /health to check when complete."}


@app.post("/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """
    Answer a natural-language question over the ingested QA documents.

    Optional filters (omit to search all documents):
    - release:  "ReleaseA" | "ReleaseB"
    - doc_type: "defect" | "test_execution" | "metadata" | "comparison"
    - k:        number of documents to retrieve (default 8)
    """
    if vectorstore is None or llm is None:
        raise HTTPException(status_code=503, detail="Service not ready.")

    if _ingest_running:
        raise HTTPException(status_code=503, detail="Ingestion in progress — please retry shortly.")

    # Ignore Swagger UI placeholder values
    release  = request.release  if request.release  not in (None, "string") else None
    doc_type = request.doc_type if request.doc_type not in (None, "string") else None

    filters: list[dict] = []
    if release:
        filters.append({"release": release})
    if doc_type:
        filters.append({"doc_type": doc_type})

    if len(filters) == 2:
        where = {"$and": filters}
    elif len(filters) == 1:
        where = filters[0]
    else:
        where = None

    search_kwargs: dict = {"k": request.k}
    if where:
        search_kwargs["filter"] = where

    docs = vectorstore.similarity_search(request.question, **search_kwargs)

    context = (
        "\n\n---\n\n".join(doc.page_content for doc in docs)
        if docs else "No relevant documents were found."
    )

    chain = PROMPT | llm | StrOutputParser()
    answer = chain.invoke({"context": context, "question": request.question})

    return QueryResponse(
        answer=answer,
        sources=[
            SourceDocument(content=doc.page_content, metadata=doc.metadata)
            for doc in docs
        ],
    )


@app.get("/debug")
async def debug(q: str = "defect categories"):
    """Inspect what the vectorstore retrieves for a query."""
    if vectorstore is None:
        raise HTTPException(status_code=503, detail="Vectorstore not loaded.")

    total = vectorstore._collection.count()
    docs = vectorstore.similarity_search(q, k=8)

    return {
        "total_docs_in_db": total,
        "query": q,
        "retrieved": [
            {"rank": i + 1, "metadata": d.metadata, "content": d.page_content}
            for i, d in enumerate(docs)
        ],
    }
