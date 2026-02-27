"""Rating submission API route."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.db import create_rating, get_generation

router = APIRouter(prefix="/api/ratings", tags=["ratings"])


class RatingRequest(BaseModel):
    generation_id: str
    rating: int = Field(ge=1, le=5)
    feedback_text: str | None = None


@router.post("")
async def submit_rating(req: RatingRequest):
    gen = get_generation(req.generation_id)
    if not gen:
        raise HTTPException(404, "Generation not found")

    rating_id = create_rating(req.generation_id, req.rating, req.feedback_text)
    return {"id": rating_id}
