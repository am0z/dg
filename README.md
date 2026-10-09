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
| `DG_DOCS_DIR` | `documents` |
| `DG_DATA_DIR` | `data` |
| `DG_HOST` / `DG_PORT` | `127.0.0.1` / `8000` |

## Customize

- **Theme:** edit the CSS variables at the top of `static/style.css`.
- **UI behavior:** `static/app.js` holds all state and API calls in one Alpine component.
- **RAG pipeline:** `rag.py` sets up the prompt, chunking, loaders, and vector store. The in-memory store saves to `data/index.json`. For larger corpora, swap in Chroma, pgvector, or similar.

## API

- `GET /api/sources`: list the indexed file names
- `POST /api/reindex`: rebuild the index from `documents/`; returns `{chunks, errors, sources}`
- `POST /api/chat`: send `{"question": "..."}`; streams back NDJSON (`{"sources": [...]}` first, then `{"token": "..."}` lines)
