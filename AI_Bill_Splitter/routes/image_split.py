import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import APIRouter, UploadFile, File, Form
from typing import Optional
from services.claude_service import split_image_bill

router = APIRouter()

@router.post("/split/image", tags=["Bill Splitting"])
async def split_image(
    file: UploadFile = File(...),
    num_people: int = Form(...),
    split_type: str = Form("equal"),
    people_names: Optional[str] = Form("")
):
    image_bytes = await file.read()
    image_content_type = file.content_type

    names_list = [n.strip() for n in people_names.split(",") if n.strip()] if people_names else []

    result = await split_image_bill(
        image_bytes=image_bytes,
        image_content_type=image_content_type,
        num_people=num_people,
        split_type=split_type,
        people_names=names_list
    )
    return result