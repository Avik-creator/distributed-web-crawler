from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app

from src.api.routes import router

app = FastAPI(
    title="Web Crawler API",
    description="Search, enqueue, and monitor the distributed web crawler",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

metrics_app = make_asgi_app()
app.mount("/prometheus", metrics_app)

app.include_router(router)


@app.get("/")
async def root() -> dict:
    return {
        "service": "web-crawler",
        "version": "0.1.0",
        "docs": "/docs",
        "ui": "/ui",
        "endpoints": {
            "search": "POST /search",
            "enqueue": "POST /urls",
            "stats": "GET /stats",
            "health": "GET /health",
            "metrics": "GET /metrics",
            "prometheus": "GET /prometheus",
        },
    }
