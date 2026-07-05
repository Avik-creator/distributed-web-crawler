from fastapi import FastAPI

from src.api.routes import router

app = FastAPI(
    title="Web Crawler API",
    description="Search, enqueue, and monitor the distributed web crawler",
    version="0.1.0",
)

app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "web-crawler",
        "version": "0.1.0",
        "docs": "/docs",
    }
