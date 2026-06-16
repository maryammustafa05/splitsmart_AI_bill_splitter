import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List
from services.service import split_manual_bill

router = APIRouter()

class Item(BaseModel):
    name: str
    price: float
    quantity: int = 1

class ManualBillRequest(BaseModel):
    num_people: int
    split_type: str
    items: List[Item]
    tax: float = 0.0
    tip: float = 0.0
    people_names: List[str] = []

@router.post("/split/manual", tags=["Bill Splitting"])
async def split_manual(request: ManualBillRequest):
    result = await split_manual_bill(
        num_people=request.num_people,
        split_type=request.split_type,
        items=[item.dict() for item in request.items],
        tax=request.tax,
        tip=request.tip,
        people_names=request.people_names
    )
    return result
