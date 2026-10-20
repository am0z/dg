"""FastAPI server: JSON API under /api, static UI at /."""

import json
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi import Path as PathParam  # noqa: E402
from fastapi.responses import StreamingResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from langchain_core.messages import HumanMessage  # noqa: E402
from langgraph.checkpoint.sqlite import SqliteSaver  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from dg.chat import build_chat, merge_preferences  # noqa: E402
from dg.rag import DATA_DIR, DOCS_DIR, RAG  # noqa: E402

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(title="dg")
rag = RAG()

DATA_DIR.mkdir(parents=True, exist_ok=True)
checkpointer = SqliteSaver(sqlite3.connect(DATA_DIR / "conversations.db", check_same_thread=False))
chat_graph = build_chat(rag, checkpointer)

THREAD_ID = {"min_length": 1, "max_length": 100, "pattern": r"^[A-Za-z0-9_-]+$"}


class Question(BaseModel):
    question: str = Field(min_length=1)
    thread_id: str = Field(**THREAD_ID)


def thread_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


@app.get("/api/sources")
def list_sources() -> list[str]:
    return rag.sources()


@app.post("/api/reindex")
def reindex() -> dict:
    if not DOCS_DIR.is_dir():
        raise HTTPException(404, f"Documents directory not found: {DOCS_DIR}")
    result = rag.reindex()
    return {**result, "sources": rag.sources()}


@app.get("/api/conversations/{thread_id}")
def get_conversation(thread_id: str = PathParam(**THREAD_ID)) -> dict:
    """Saved messages (with each answer's sources) and preferences for a conversation."""
    state = chat_graph.get_state(thread_config(thread_id)).values
    messages = [
        {
            "role": "user" if m.type == "human" else "assistant",
            "content": m.content,
            "sources": m.additional_kwargs.get("sources", []),
        }
        for m in state.get("messages", [])
        if m.type in ("human", "ai")
    ]
    return {"messages": messages, "preferences": state.get("preferences", {})}


@app.post("/api/chat")
def chat(q: Question) -> StreamingResponse:
    """Streams NDJSON events in order: {"preferences": {...}}, {"sources": [...]},
    then {"token": "..."} lines. The conversation is saved under q.thread_id."""
    graph_input = {"messages": [HumanMessage(q.question)]}
    saved_prefs = chat_graph.get_state(thread_config(q.thread_id)).values.get("preferences", {})

    def events():
        for mode, data in chat_graph.stream(
            graph_input, thread_config(q.thread_id), stream_mode=["updates", "messages"]
        ):
            if mode == "messages":
                chunk, meta = data
                if meta.get("langgraph_node") == "generate" and chunk.content:
                    yield json.dumps({"token": chunk.content}) + "\n"
            elif "analyze" in data:
                prefs = merge_preferences(saved_prefs, data["analyze"]["preferences"])
                yield json.dumps({"preferences": prefs}) + "\n"
            elif "retrieve" in data:
                yield json.dumps({"sources": data["retrieve"]["sources"]}) + "\n"

    return StreamingResponse(events(), media_type="application/x-ndjson")


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
