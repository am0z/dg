import os


def main() -> None:
    import uvicorn

    uvicorn.run(
        "dg.app:app",
        host=os.getenv("DG_HOST", "127.0.0.1"),
        port=int(os.getenv("DG_PORT", "8000")),
        reload=os.getenv("DG_RELOAD", "1") == "1",
    )
