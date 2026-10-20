"""Conversational RAG as a LangGraph graph with per-conversation persistent state.

Each turn runs: analyze -> retrieve -> generate.
  analyze:  rewrites the latest message into a standalone search query using the
            chat history, and picks up any preferences the user stated.
  retrieve: searches the index with that query.
  generate: answers from the retrieved context, history, and preferences.

A checkpointer saves the full state after every turn, keyed by thread_id, so a
conversation (messages, preferences, last sources) survives server restarts.
"""

import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, AnyMessage, SystemMessage, trim_messages
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from dg.rag import CHAT_MODEL, RAG

# How many recent messages the model sees. Older turns stay saved but aren't sent.
HISTORY_MESSAGES = int(os.getenv("DG_HISTORY_MESSAGES", "20"))


def merge_preferences(old: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    """Reducer: later values win; an empty value forgets that preference."""
    merged = {**old, **new}
    return {k: v for k, v in merged.items() if v}


class ChatState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    # Custom state: add fields here and they are persisted per conversation.
    preferences: Annotated[dict[str, str], merge_preferences]
    query: str
    sources: list[dict]


class Preference(BaseModel):
    key: str = Field(description="Short snake_case name, e.g. 'language', 'answer_length', 'tone'")
    value: str = Field(description="The preference, or an empty string if the user asked to drop it")


class Analysis(BaseModel):
    search_query: str = Field(
        description="The latest user message rewritten as a standalone search query, "
        "resolving pronouns and references using the conversation"
    )
    preference_updates: list[Preference] = Field(
        description="Preferences about how to answer that the user stated in their LATEST "
        "message only (language, length, tone, format, ...). Empty if none."
    )


ANALYZE_PROMPT = """You prepare a document search for a question-answering assistant.

Current preferences: {preferences}

Rewrite the user's latest message as a standalone search query and extract any \
answer preferences it states. Don't treat questions about content as preferences."""

ANSWER_PROMPT = """Answer the user's latest message using only the context below and \
the conversation so far. If the context doesn't contain the answer, say you don't know. \
Cite sources by their [number].

User preferences (follow these): {preferences}

Context:
{context}"""


def format_preferences(prefs: dict[str, str]) -> str:
    return "; ".join(f"{k}: {v}" for k, v in prefs.items()) or "none"


def build_chat(rag: RAG, checkpointer: BaseCheckpointSaver):
    llm = ChatOpenAI(model=CHAT_MODEL)
    analyzer = llm.with_structured_output(Analysis)

    def recent(messages: list[AnyMessage]) -> list[AnyMessage]:
        return trim_messages(
            messages, max_tokens=HISTORY_MESSAGES, token_counter=len, strategy="last", start_on="human"
        )

    def analyze(state: ChatState) -> dict:
        prefs = state.get("preferences", {})
        system = SystemMessage(ANALYZE_PROMPT.format(preferences=format_preferences(prefs)))
        result: Analysis = analyzer.invoke([system, *recent(state["messages"])])
        updates = {p.key: p.value for p in result.preference_updates}
        return {"query": result.search_query, "preferences": updates}

    def retrieve(state: ChatState) -> dict:
        docs = rag.retrieve(state["query"])
        return {
            "sources": [
                {"source": d.metadata.get("source"), "page": d.metadata.get("page"), "text": d.page_content}
                for d in docs
            ]
        }

    def generate(state: ChatState) -> dict:
        context = "\n\n".join(f"[{i}] {s['text']}" for i, s in enumerate(state["sources"], 1))
        system = SystemMessage(
            ANSWER_PROMPT.format(
                preferences=format_preferences(state.get("preferences", {})), context=context
            )
        )
        response = llm.invoke([system, *recent(state["messages"])])
        # Keep this turn's sources on the message so reloaded history can show them.
        reply = AIMessage(content=response.content, id=response.id, additional_kwargs={"sources": state["sources"]})
        return {"messages": [reply]}

    graph = StateGraph(ChatState)
    graph.add_node("analyze", analyze)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_edge(START, "analyze")
    graph.add_edge("analyze", "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", END)
    return graph.compile(checkpointer=checkpointer)
