import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.lifespan import lifespan
from app.core.security import (
    ALLOW_CREDENTIALS,
    ALLOWED_HEADERS,
    ALLOWED_METHODS,
    ALLOWED_ORIGINS,
    limit_request_size,
    rate_limit,
)
from app.routes import (
    chat,
    connections,
    embeddings,
    images,
    imports,
    notes,
    organize,
    search,
    stats,
    tags,
)

app = FastAPI(title="Google Keep Vibe Search", lifespan=lifespan)

# See app/core/security.py: this app is single-user and loopback-only, so the origin
# list is enumerated and credentials are off.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=ALLOW_CREDENTIALS,
    allow_methods=ALLOWED_METHODS,
    allow_headers=ALLOWED_HEADERS,
)

# Registration order is reversed at request time: the size cap is added last so it runs
# first, and an oversized body is refused before the limiter spends a slot on it.
app.middleware("http")(rate_limit)
app.middleware("http")(limit_request_size)

app.include_router(search.router)
app.include_router(chat.router)
app.include_router(notes.router)
app.include_router(tags.router)
app.include_router(stats.router)
app.include_router(images.router)
app.include_router(embeddings.router)
app.include_router(connections.router)
app.include_router(organize.router)
app.include_router(imports.router)

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
