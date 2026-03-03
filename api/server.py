import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routes import router as api_router
from api.streaming import streaming_router

app = FastAPI(title="Tessiture API", version="0.1.0")

cors_origins = [
    origin.strip()
    for origin in os.getenv("TESSITURE_CORS_ORIGINS", "http://localhost,http://127.0.0.1").split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(streaming_router)

frontend_dist = Path(os.getenv("TESSITURE_FRONTEND_DIST", "frontend/dist"))
if frontend_dist.exists() and (frontend_dist / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
