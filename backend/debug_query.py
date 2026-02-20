"""
debug_query.py - Inspect what ChromaDB retrieves and what context is sent to the LLM.

Usage:
    python debug_query.py "What are the major defect categories?"
    python debug_query.py "What are the major defect categories?" --release ReleaseA
    python debug_query.py "What are the major defect categories?" --k 10
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

load_dotenv()

CHROMA_DIR = Path(__file__).parent / "chroma_db"
COLLECTION_NAME = "qa_documents"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"

SEPARATOR = "-" * 70


def debug_query(question: str, release: str = None, doc_type: str = None, k: int = 8):
    # --- Load vectorstore ---
    if not CHROMA_DIR.exists():
        print("ERROR: ChromaDB not found. Run python ingest.py first.")
        return

    print(f"\n{'='*70}")
    print(f"  QUERY DEBUG")
    print(f"{'='*70}")
    print(f"  Question : {question}")
    print(f"  Release  : {release or 'all'}")
    print(f"  Doc type : {doc_type or 'all'}")
    print(f"  k        : {k}")
    print(f"{'='*70}\n")

    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    vectorstore = Chroma(
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=str(CHROMA_DIR),
    )

    # Report total docs in collection
    total = vectorstore._collection.count()
    print(f"Total documents in ChromaDB: {total}\n")

    if total == 0:
        print("ERROR: ChromaDB is empty. Run python ingest.py first.")
        return

    # --- Build filter ---
    filters = []
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

    search_kwargs = {"k": k}
    if where:
        search_kwargs["filter"] = where

    # --- Retrieve with scores ---
    results = vectorstore.similarity_search_with_score(question, **search_kwargs)

    print(f"Retrieved {len(results)} document(s):\n")

    for i, (doc, score) in enumerate(results, 1):
        print(f"{SEPARATOR}")
        print(f"  Document {i}  |  Score: {score:.4f}  |  "
              f"release={doc.metadata.get('release')}  "
              f"doc_type={doc.metadata.get('doc_type')}")
        print(SEPARATOR)
        print(doc.page_content)
        print()

    # --- Show the exact context string the LLM receives ---
    print(f"\n{'='*70}")
    print("  FULL CONTEXT PASSED TO LLM")
    print(f"{'='*70}\n")
    context = "\n\n---\n\n".join(doc.page_content for doc, _ in results) if results else "No relevant documents were found."
    print(context)
    print(f"\n{'='*70}")
    print("  END OF CONTEXT")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug RAG retrieval context")
    parser.add_argument("question", help="The question to retrieve context for")
    parser.add_argument("--release", default=None, help="Filter by release: ReleaseA or ReleaseB")
    parser.add_argument("--doc_type", default=None, help="Filter by doc_type: defect, test_execution, metadata")
    parser.add_argument("--k", type=int, default=8, help="Number of documents to retrieve")
    args = parser.parse_args()

    debug_query(args.question, args.release, args.doc_type, args.k)
