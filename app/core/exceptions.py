from fastapi import HTTPException


class SearchEngineNotInitialized(HTTPException):
    def __init__(self):
        super().__init__(status_code=503, detail="Search engine not initialized yet")


class ChatServiceNotInitialized(HTTPException):
    def __init__(self):
        super().__init__(status_code=503, detail="Chat service not initialized yet")


class ImageSearchDisabled(HTTPException):
    def __init__(self):
        super().__init__(status_code=400, detail="Image search is not enabled")


class ImageProcessorNotInitialized(HTTPException):
    def __init__(self):
        super().__init__(
            status_code=503, detail="Image processor not initialized"
        )


class InvalidFileType(HTTPException):
    def __init__(self, expected: str):
        super().__init__(
            status_code=400, detail=f"Uploaded file must be {expected}"
        )


class NoteNotTagged(HTTPException):
    def __init__(self, note_id: str):
        super().__init__(status_code=404, detail=f"Note '{note_id}' is not tagged")


class TagNotFound(HTTPException):
    def __init__(self, tag_name: str):
        super().__init__(
            status_code=404, detail=f"No notes found with tag '{tag_name}'"
        )


class SessionNotFound(HTTPException):
    def __init__(self, session_id: str):
        super().__init__(
            status_code=404, detail=f"Chat session '{session_id}' not found"
        )
