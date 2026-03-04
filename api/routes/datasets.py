"""Dataset browsing API routes."""

from fastapi import APIRouter, Query

from api.db import get_dataset, get_dataset_stats, get_records, get_generations_grouped_by_method, list_datasets
from api.s3 import resolve_url

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("")
async def list_datasets_route():
    return list_datasets()


@router.get("/{dataset_id}/records")
async def get_records_route(
    dataset_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    crash_type: str | None = None,
    search: str | None = None,
):
    records, total = get_records(dataset_id, page=page, per_page=per_page,
                                  crash_type=crash_type, search=search)

    # Attach generation summaries grouped by method
    if records:
        record_ids = [r["id"] for r in records]
        gen_map = get_generations_grouped_by_method(record_ids)
        for rid_gens in gen_map.values():
            for gen in rid_gens.values():
                gen["mp4_url"] = resolve_url(gen.get("mp4_url"))
                gen["thumbnail_url"] = resolve_url(gen.get("thumbnail_url"))
        for r in records:
            r["generations"] = gen_map.get(r["id"], {})

    return {
        "records": records,
        "total": total,
        "page": page,
        "per_page": per_page,
    }


@router.get("/{dataset_id}/stats")
async def get_stats_route(dataset_id: int):
    return get_dataset_stats(dataset_id)
