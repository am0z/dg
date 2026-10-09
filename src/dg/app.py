"""FastAPI server: JSON API under /api, static UI at /."""

import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from dg.rag import DOCS_DIR, RAG  # noqa: E402

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="dg")
rag = RAG()


class Question(BaseModel):
    question: str


@app.get("/api/sources")
def list_sources() -> list[str]:
    return rag.sources()


@app.post("/api/reindex")
def reindex() -> dict:
    if not DOCS_DIR.is_dir():
        raise HTTPException(404, f"Documents directory not found: {DOCS_DIR}")
    result = rag.reindex()
    return {**result, "sources": rag.sources()}


@app.post("/api/chat")
def chat(q: Question) -> StreamingResponse:
    """Streams NDJSON: one {"sources": [...]} line, then {"token": "..."} lines."""
    docs = rag.retrieve(q.question)

    def events():
        sources = [
            {"source": d.metadata.get("source"), "page": d.metadata.get("page"), "text": d.page_content}
            for d in docs
        ]
        yield json.dumps({"sources": sources}) + "\n"
        for token in rag.stream_answer(q.question, docs):
            yield json.dumps({"token": token}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
