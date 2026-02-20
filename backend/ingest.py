"""
ingest.py - LLM-driven Q&A chunking strategy for RAG over QA Excel documents.

Strategy
--------
Instead of chunking by row or arbitrary text size, we use Claude to read each
dataset and generate every plausible question a user might ask, paired with an
accurate answer computed from the data.  Each Q&A pair is stored as one
ChromaDB document.

Why this works better for retrieval
------------------------------------
User queries are natural-language questions.  Storing pre-generated questions
as document content means cosine similarity between the user query and a stored
question is naturally high — far higher than matching a query against a raw
spreadsheet row.

Three passes are made:
  1. Per-file pass   — questions scoped to one file (e.g. Release A defects)
  2. Per-release pass — cross-file questions within a release (defects + tests)
  3. Cross-release pass — comparison questions between Release A and Release B

Usage
-----
    python ingest.py
"""

import json
import os
import shutil

import groq as groq_sdk
import pandas as pd
from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_core.documents import Document
from pathlib import Path

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DOCS_DIR = Path(__file__).parent.parent / "docs"
CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "qa_documents"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
ANALYSIS_MODEL = "llama-3.3-70b-versatile"   # Groq free tier — fast + capable

# ---------------------------------------------------------------------------
# Data helpers — turn DataFrames into rich text for the LLM prompt
# ---------------------------------------------------------------------------

def df_to_markdown(df: pd.DataFrame, max_rows: int = 60) -> str:
    """Return a markdown table. Truncate only if truly necessary."""
    return df.head(max_rows).to_markdown(index=False)


def defect_stats(df: pd.DataFrame) -> str:
    lines = [f"Total defects: {len(df)}"]
    for col in ["Component", "Severity", "Priority", "Status"]:
        counts = df[col].value_counts()
        lines.append(f"{col}: " + ", ".join(f"{k} ({v})" for k, v in counts.items()))
    open_n = (df["Status"] != "Closed").sum()
    closed_n = (df["Status"] == "Closed").sum()
    lines.append(f"Open: {open_n}  |  Closed: {closed_n}")
    lines.append(f"Date range: {df['Created Date'].min().date()} → {df['Created Date'].max().date()}")
    return "\n".join(lines)


def test_stats(df: pd.DataFrame) -> str:
    lines = [f"Total test runs: {len(df)}"]
    for col in ["Suite", "Status", "Tester", "Automation"]:
        counts = df[col].value_counts()
        lines.append(f"{col}: " + ", ".join(f"{k} ({v})" for k, v in counts.items()))
    linked = df["Linked Defect ID"].notna().sum()
    lines.append(f"Runs linked to a defect: {linked}  |  No linked defect: {len(df) - linked}")
    return "\n".join(lines)


def metadata_text(df: pd.DataFrame) -> str:
    return "\n".join(
        f"{row['Metric']}: {row['Value']}"
        for _, row in df.iterrows()
        if pd.notna(row.get("Value"))
    )

# ---------------------------------------------------------------------------
# LLM call — generate Q&A pairs from a prompt
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a QA analyst assistant. "
    "Generate comprehensive, accurate question-and-answer pairs from the provided data. "
    "Return ONLY a valid JSON array — no markdown fences, no commentary:\n"
    '[{"question": "...", "answer": "..."}, ...]'
)

def _call_llm(client: groq_sdk.Groq, user_prompt: str) -> list[dict]:
    """Call Groq and return parsed list of {question, answer} dicts."""
    msg = client.chat.completions.create(
        model=ANALYSIS_MODEL,
        max_tokens=4096,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
    )
    raw = msg.choices[0].message.content.strip()
    # Robustly extract the JSON array even if model adds surrounding text
    start, end = raw.find("["), raw.rfind("]") + 1
    if start == -1 or end == 0:
        print("    [warn] Could not locate JSON array in LLM response — skipping.")
        return []
    return json.loads(raw[start:end])


def pairs_to_documents(pairs: list[dict], metadata: dict) -> list[Document]:
    docs = []
    for pair in pairs:
        q = pair.get("question", "").strip()
        a = pair.get("answer", "").strip()
        if q and a:
            docs.append(Document(
                page_content=f"Q: {q}\nA: {a}",
                metadata={**metadata, "question": q},
            ))
    return docs

# ---------------------------------------------------------------------------
# Per-file Q&A generation prompts
# ---------------------------------------------------------------------------

def qa_for_defects(client: groq_sdk.Groq, df: pd.DataFrame,
                   release: str, filename: str) -> list[Document]:
    prompt = f"""
You are analyzing defect tracking data for {release} from {filename}.

=== DATA (markdown table) ===
{df_to_markdown(df)}

=== COMPUTED STATISTICS ===
{defect_stats(df)}

Generate ALL questions a user might reasonably ask about this defect data.
Cover every angle:
- Overall counts and totals
- Component breakdown and which components are most/least affected
- Severity and priority distributions
- Open vs closed defects and resolution rates
- Specific defects by component, severity, priority, or status
- Date trends (when were most defects created / resolved?)
- Which defects are still open?
- Any notable patterns or outliers
- Questions about specific issue keys or summaries

Provide precise, data-backed answers.
""".strip()

    print(f"    Generating defect Q&A pairs for {release} ...")
    pairs = _call_llm(client, prompt)
    docs = pairs_to_documents(pairs, {
        "source": filename, "doc_type": "defect", "release": release,
    })
    print(f"    -> {len(docs)} pairs")
    return docs


def qa_for_tests(client: groq_sdk.Groq, df: pd.DataFrame,
                 release: str, filename: str) -> list[Document]:
    prompt = f"""
You are analyzing test execution data for {release} from {filename}.

=== DATA (markdown table) ===
{df_to_markdown(df)}

=== COMPUTED STATISTICS ===
{test_stats(df)}

Generate ALL questions a user might reasonably ask about this test execution data.
Cover every angle:
- Total runs and pass/fail/retest/blocked counts
- Pass rate and failure rate (as percentages)
- Which suites have the most failures or retests?
- Automation vs manual split
- Which testers ran the most tests?
- Tests linked to defects — which suites have linked defects?
- Longest/shortest execution times
- Specific test cases and their statuses
- Any test cases that need retesting?
- Patterns across suites or testers

Provide precise, data-backed answers.
""".strip()

    print(f"    Generating test execution Q&A pairs for {release} ...")
    pairs = _call_llm(client, prompt)
    docs = pairs_to_documents(pairs, {
        "source": filename, "doc_type": "test_execution", "release": release,
    })
    print(f"    -> {len(docs)} pairs")
    return docs


def qa_for_metadata(client: groq_sdk.Groq, df: pd.DataFrame,
                    release: str, filename: str) -> list[Document]:
    prompt = f"""
You are analyzing release metadata for {release} from {filename}.

=== METADATA ===
{metadata_text(df)}

Generate ALL questions a user might ask about this release's metadata and
general information. Cover release name, dates, team size, scope, goals,
and any other metrics present.

Provide precise answers.
""".strip()

    print(f"    Generating metadata Q&A pairs for {release} ...")
    pairs = _call_llm(client, prompt)
    docs = pairs_to_documents(pairs, {
        "source": filename, "doc_type": "metadata", "release": release,
    })
    print(f"    -> {len(docs)} pairs")
    return docs

# ---------------------------------------------------------------------------
# Cross-release comparison Q&A
# ---------------------------------------------------------------------------

def qa_cross_release(
    client: groq_sdk.Groq,
    defects_a: pd.DataFrame, tests_a: pd.DataFrame, meta_a: pd.DataFrame,
    defects_b: pd.DataFrame, tests_b: pd.DataFrame, meta_b: pd.DataFrame,
) -> list[Document]:
    prompt = f"""
You are comparing two software releases: Release A and Release B.

=== RELEASE A — DEFECT STATISTICS ===
{defect_stats(defects_a)}

=== RELEASE B — DEFECT STATISTICS ===
{defect_stats(defects_b)}

=== RELEASE A — TEST EXECUTION STATISTICS ===
{test_stats(tests_a)}

=== RELEASE B — TEST EXECUTION STATISTICS ===
{test_stats(tests_b)}

=== RELEASE A — METADATA ===
{metadata_text(meta_a)}

=== RELEASE B — METADATA ===
{metadata_text(meta_b)}

Generate ALL cross-release comparison questions a user might ask.
Cover every angle:
- Which release had more defects overall?
- How does severity/priority distribution differ between releases?
- Which components improved or worsened between releases?
- How do pass rates compare between releases?
- Which release had better test coverage?
- Which release had more automated tests?
- Overall quality trend: is Release B better or worse than Release A?
- How do open defect counts compare?
- Tester productivity comparison
- Suite-level comparison of failures

Provide precise, data-backed answers referencing both releases.
""".strip()

    print("    Generating cross-release comparison Q&A pairs ...")
    pairs = _call_llm(client, prompt)
    docs = pairs_to_documents(pairs, {
        "source": "cross_release",
        "doc_type": "comparison",
        "release": "all",
    })
    print(f"    -> {len(docs)} pairs")
    return docs

# ---------------------------------------------------------------------------
# Main ingestion orchestrator
# ---------------------------------------------------------------------------

def ingest() -> Chroma:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set. Add it to backend/.env")

    client = groq_sdk.Groq(api_key=api_key)

    print(f"Docs directory : {DOCS_DIR.resolve()}")
    print(f"ChromaDB path  : {CHROMA_DIR.resolve()}")
    print(f"Analysis model : {ANALYSIS_MODEL}\n")

    # --- Load all DataFrames up front ---
    def load(name: str) -> tuple[pd.DataFrame, str]:
        matches = list(DOCS_DIR.glob(f"*{name}*.xlsx"))
        if not matches:
            raise FileNotFoundError(f"No file matching *{name}*.xlsx in {DOCS_DIR}")
        return pd.read_excel(matches[0]), matches[0].name

    (defects_a, fn_da) = load("ReleaseA_Defects")
    (tests_a,   fn_ta) = load("ReleaseA_TestExecution")
    (meta_a,    fn_ma) = load("ReleaseA_Meta")
    (defects_b, fn_db) = load("ReleaseB_Defects")
    (tests_b,   fn_tb) = load("ReleaseB_TestExecution")
    (meta_b,    fn_mb) = load("ReleaseB_Meta")

    all_docs: list[Document] = []

    # --- Pass 1: per-file Q&A ---
    print("Pass 1: per-file Q&A generation")
    all_docs += qa_for_defects(client, defects_a, "ReleaseA", fn_da)
    all_docs += qa_for_tests(client, tests_a, "ReleaseA", fn_ta)
    all_docs += qa_for_metadata(client, meta_a, "ReleaseA", fn_ma)
    all_docs += qa_for_defects(client, defects_b, "ReleaseB", fn_db)
    all_docs += qa_for_tests(client, tests_b, "ReleaseB", fn_tb)
    all_docs += qa_for_metadata(client, meta_b, "ReleaseB", fn_mb)

    # --- Pass 2: cross-release comparison Q&A ---
    print("\nPass 2: cross-release comparison Q&A generation")
    all_docs += qa_cross_release(
        client, defects_a, tests_a, meta_a, defects_b, tests_b, meta_b
    )

    print(f"\nTotal Q&A documents generated: {len(all_docs)}")

    # --- Clear stale DB and re-embed ---
    if CHROMA_DIR.exists():
        print("Clearing existing ChromaDB ...")
        shutil.rmtree(CHROMA_DIR)

    print(f"Loading embedding model: {EMBEDDING_MODEL}")
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)

    print("Writing to ChromaDB ...")
    vectorstore = Chroma.from_documents(
        documents=all_docs,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_DIR),
    )

    print(f"\nDone. {len(all_docs)} Q&A documents stored in collection '{COLLECTION_NAME}'.")
    return vectorstore


if __name__ == "__main__":
    ingest()
