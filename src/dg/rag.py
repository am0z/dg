"""Document index: load and chunk files from DOCS_DIR, embed them, and search them."""

import os
import threading
from pathlib import Path

from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_core.documents import Document
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

DOCS_DIR = Path(os.getenv("DG_DOCS_DIR", "documents"))
DATA_DIR = Path(os.getenv("DG_DATA_DIR", "data"))
INDEX_PATH = DATA_DIR / "index.json"
CHAT_MODEL = os.getenv("DG_CHAT_MODEL", "gpt-4.1-mini")
EMBED_MODEL = os.getenv("DG_EMBED_MODEL", "text-embedding-3-small")
TOP_K = int(os.getenv("DG_TOP_K", "4"))

LOADERS = {
    ".pdf": PyPDFLoader,
    ".txt": TextLoader,
    ".md": TextLoader,
}

def source_name(path: Path) -> str:
    """Name a file by its path relative to DOCS_DIR, or by its filename if outside it."""
    try:
        return path.resolve().relative_to(DOCS_DIR.resolve()).as_posix()
    except ValueError:
        return path.name


class RAG:
    def __init__(self) -> None:
        self.embeddings = OpenAIEmbeddings(model=EMBED_MODEL)
        self.splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)
        if INDEX_PATH.exists():
            self.store = InMemoryVectorStore.load(str(INDEX_PATH), self.embeddings)
        else:
            self.store = InMemoryVectorStore(self.embeddings)
        self._reindex_lock = threading.Lock()

    def reindex(self) -> dict:
        """Rebuild the index from every supported file in DOCS_DIR.

        Builds into a fresh store and swaps it in at the end, so questions asked
        mid-reindex still search the old index. Files that fail to load are
        skipped and reported rather than aborting the whole run.
        """
        with self._reindex_lock:
            store = InMemoryVectorStore(self.embeddings)
            chunks, errors = {}, {}
            for path in sorted(DOCS_DIR.rglob("*")):
                if not (path.is_file() and path.suffix.lower() in LOADERS):
                    continue
                source = source_name(path)
                try:
                    chunks[source] = self._index_file(store, path, source)
                except Exception as e:
                    errors[source] = str(e)
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = INDEX_PATH.with_suffix(".tmp")
            store.dump(str(tmp))
            tmp.replace(INDEX_PATH)
            self.store = store
            return {"chunks": chunks, "errors": errors}

    def _index_file(self, store: InMemoryVectorStore, path: Path, source: str) -> int:
        docs = LOADERS[path.suffix.lower()](str(path)).load()
        for doc in docs:
            doc.metadata["source"] = source
        chunks = self.splitter.split_documents(docs)
        if chunks:
            store.add_documents(chunks)
        return len(chunks)

    def sources(self) -> list[str]:
        return sorted({doc["metadata"].get("source", "?") for doc in self.store.store.values()})

    def retrieve(self, question: str) -> list[Document]:
        return self.store.similarity_search(question, k=TOP_K)
