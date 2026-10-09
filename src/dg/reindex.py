"""Rebuild the vector index from every supported file in the documents directory.

Usage: uv run dg-reindex
"""

import sys

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    from dg.rag import DOCS_DIR, INDEX_PATH, RAG

    if not DOCS_DIR.is_dir():
        sys.exit(f"Documents directory not found: {DOCS_DIR.resolve()}")

    print(f"Reindexing {DOCS_DIR.resolve()} ...")
    result = RAG().reindex()
    chunks, errors = result["chunks"], result["errors"]
    for source, count in chunks.items():
        print(f"  {source}: {count} chunks")
    for source, error in errors.items():
        print(f"  {source}: FAILED ({error})", file=sys.stderr)
    print(f"Indexed {len(chunks)} files ({sum(chunks.values())} chunks) -> {INDEX_PATH}")
    print("If the server is running, restart it or use the Reindex button to load the new index.")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
