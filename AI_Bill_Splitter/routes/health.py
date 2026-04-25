from fastapi import APIRouter

router = APIRouter()

@router.get("/health", tags=["Health"])
def health_check():
    return {"status": "running", "message": "AI Bill Splitter backend is up and running."}