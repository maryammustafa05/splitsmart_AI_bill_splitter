from fastapi import APIRouter
from services.claude_service import get_expense_history

router = APIRouter()

@router.get("/history", tags=["Expense History"])
def get_history():
    history = get_expense_history()
    return {
        "success": True,
        "total": len(history),
        "history": history
    }