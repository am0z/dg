# dg

A RAG chat app: drop documents in a folder, index them, then ask questions about them.

- **Backend:** FastAPI + LangChain + OpenAI (`src/dg/`)
- **Frontend:** Alpine.js with no build step (`src/dg/static/`)

## Run

```sh
uv sync
uv run dg          # http://127.0.0.1:8000
```

You need `OPENAI_API_KEY` in `.env`.

## Documents and index

Put `.pdf`, `.txt` and `.md` files in `documents/`. Subfolders work too. Then click **Reindex documents** in the UI, or run:

```sh
uv run dg-reindex  # rebuild the index from documents/ on the command line
```

The index is stored permanently on disk at `data/index.json`. The UI button reloads the index straight away. After a command-line reindex, restart the server or click the button. Reindexing always rebuilds from scratch, so deleted files drop out of the index. A file that fails to load is skipped and reported; it doesn't abort the run.

## Configure

| Env var | Default |
|---|---|
| `DG_CHAT_MODEL` | `gpt-4.1-mini` |
| `DG_EMBED_MODEL` | `text-embedding-3-small` |
| `DG_TOP_K` | `4` |
| `DG_HISTORY_MESSAGES` | `20` (recent messages the model sees) |
| `DG_DOCS_DIR` | `documents` |
| `DG_DATA_DIR` | `data` |
| `DG_HOST` / `DG_PORT` | `127.0.0.1` / `8000` |

## Conversations

Each browser keeps one ongoing conversation, and it survives page reloads and server restarts. **New chat** starts a fresh one. Every conversation's messages, sources, and state are saved to `data/conversations.db` (SQLite) by a LangGraph checkpointer.

Each turn:

1. **Analyze:** rewrites the latest message into a standalone search query using the chat history, so a follow-up like "where was she based?" searches properly. It also picks up stated preferences like "answer in Spanish" or "keep it short".
2. **Retrieve:** searches the index with that query.
3. **Generate:** answers from the retrieved context, recent history, and the remembered preferences. The sidebar shows the preferences under *Remembered*.

## Customize

- **Theme:** edit the CSS variables at the top of `static/style.css`.
- **UI behavior:** `static/app.js` holds all state and API calls in one Alpine component.
- **Conversation pipeline:** `chat.py` is a LangGraph graph (analyze → retrieve → generate) with the prompts and the agent state schema. To add custom state, add a field to `ChatState`; it's saved per conversation automatically.
- **Index:** `rag.py` handles chunking, loaders, and the vector store. The in-memory store saves to `data/index.json`. For larger corpora, swap in Chroma, pgvector, or similar.

## API

- `GET /api/sources`: list the indexed file names
- `POST /api/reindex`: rebuild the index from `documents/`; returns `{chunks, errors, sources}`
- `POST /api/chat`: send `{"question": "...", "thread_id": "..."}`; streams back NDJSON (`{"preferences": {...}}`, then `{"sources": [...]}`, then `{"token": "..."}` lines)
- `GET /api/conversations/{thread_id}`: saved messages (each answer with its sources) and preferences
