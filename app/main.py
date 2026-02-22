import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.lifespan import lifespan
from app.routes import chat, embeddings, health, images, notes, search, stats, tags

app = FastAPI(title="Google Keep Vibe Search", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(search.router)
app.include_router(chat.router)
app.include_router(notes.router)
app.include_router(tags.router)
app.include_router(stats.router)
app.include_router(images.router)
app.include_router(embeddings.router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host=settings.host, port=settings.port, reload=True)
