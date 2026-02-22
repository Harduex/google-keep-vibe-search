from fastapi import APIRouter, Request

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
def health_check(request: Request):
    """Lightweight health check that works even during startup.

    Returns service readiness so the frontend can distinguish
    "backend is starting" from "backend is down".
    """
    note_service = getattr(request.app.state, "note_service", None)
    search_service = getattr(request.app.state, "search_service", None)
    chat_service = getattr(request.app.state, "chat_service", None)
    lancedb_service = getattr(request.app.state, "lancedb_service", None)
    graph_service = getattr(request.app.state, "graph_service", None)
    raptor_service = getattr(request.app.state, "raptor_service", None)

    ready = chat_service is not None

    return {
        "status": "ok",
        "ready": ready,
        "total_notes": len(note_service.notes) if note_service else 0,
        "services": {
            "notes": note_service is not None,
            "search": search_service is not None,
            "chat": chat_service is not None,
            "lancedb": lancedb_service is not None,
            "graphrag": graph_service is not None,
            "raptor": raptor_service is not None,
        },
    }
