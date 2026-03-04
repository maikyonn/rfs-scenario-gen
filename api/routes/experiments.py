"""Experiment CRUD + results API routes."""

import json
import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from api.db import (
    create_experiment,
    create_generation,
    get_dataset,
    get_experiment,
    get_experiment_progress,
    get_experiment_record_ids,
    get_experiment_summary,
    get_generations_grouped_by_method,
    get_records,
    get_records_by_ids,
    get_records_needing_enrichment,
    list_experiments,
    update_experiment,
    update_record_tldr_and_road_context,
)
from api.s3 import resolve_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/experiments", tags=["experiments"])


def _enrich_records(records: list[dict]):
    """Generate TLDR + road_context for records that need them."""
    record_ids = [r["id"] for r in records]
    need = get_records_needing_enrichment(record_ids)
    if not need:
        return

    from api.backfill_records import SYSTEM, _parse_response
    from api.pipeline import _call_bedrock

    for rec in need:
        try:
            messages = [{"role": "user", "content": rec["text_desc"]}]
            text, _, _ = _call_bedrock(messages, SYSTEM)
            tldr, road_context = _parse_response(text)
            update_record_tldr_and_road_context(rec["id"], tldr, road_context)
        except Exception as e:
            logger.warning("Enrichment failed for record %d: %s", rec["id"], e)


class CreateExperimentRequest(BaseModel):
    name: str
    dataset_id: int
    methods: list[str]
    crash_type_filter: str | None = None
    max_records: int = 50  # hard cap at 50 for R&D testing


@router.post("")
async def create_experiment_route(req: CreateExperimentRequest):
    dataset = get_dataset(req.dataset_id)
    if not dataset:
        raise HTTPException(404, "Dataset not found")

    # Get eligible record IDs (hard cap at 50)
    capped = min(req.max_records, 50)
    records, total = get_records(
        req.dataset_id,
        page=1,
        per_page=capped,
        crash_type=req.crash_type_filter,
    )

    if not records:
        raise HTTPException(400, "No matching records found")

    record_ids = [r["id"] for r in records]

    # Enrich records (TLDR + road_context) in background thread
    import threading
    threading.Thread(target=_enrich_records, args=(records,), daemon=True).start()

    exp_id = create_experiment(
        name=req.name,
        dataset_id=req.dataset_id,
        methods=req.methods,
        record_ids=record_ids,
    )

    # Create generation rows and enqueue jobs
    from api.batch_worker import enqueue_job

    total_jobs = 0
    for record in records:
        for method in req.methods:
            gen_id = create_generation(
                record_id=record["id"],
                method=method,
                experiment_id=exp_id,
            )
            enqueue_job(
                generation_id=gen_id,
                method=method,
                description=record["text_desc"],
                record_id=record["id"],
                road_context=record.get("road_context"),
            )
            total_jobs += 1

    update_experiment(exp_id, status="running")
    logger.info("Experiment %d created: %d records × %d methods = %d jobs",
                exp_id, len(records), len(req.methods), total_jobs)

    return {"id": exp_id, "total_jobs": total_jobs, "status": "running"}


@router.get("")
async def list_experiments_route():
    experiments = list_experiments()
    # Attach progress to each
    for exp in experiments:
        exp["progress"] = get_experiment_progress(exp["id"])
    return experiments


@router.get("/{exp_id}")
async def get_experiment_route(exp_id: int):
    exp = get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")

    progress = get_experiment_progress(exp_id)
    total = sum(
        p["completed"] + p["failed"] + p["pending"]
        for p in progress.values()
    )

    # Auto-complete if all done
    all_done = all(p["pending"] == 0 for p in progress.values()) if progress else False
    if all_done and exp["status"] == "running":
        update_experiment(exp_id, status="complete")
        exp["status"] = "complete"

    return {
        **exp,
        "total": total,
        "progress": progress,
    }


@router.get("/{exp_id}/results")
async def get_results_route(
    exp_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    exp = get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")

    all_record_ids = get_experiment_record_ids(exp_id)
    total = len(all_record_ids)

    offset = (page - 1) * per_page
    page_record_ids = all_record_ids[offset : offset + per_page]

    if not page_record_ids:
        return {"results": [], "total": total, "page": page, "per_page": per_page}

    gen_map = get_generations_grouped_by_method(page_record_ids, experiment_id=exp_id)

    record_map = get_records_by_ids(page_record_ids)

    # Resolve S3 keys to presigned URLs in generation data
    for rid_gens in gen_map.values():
        for gen in rid_gens.values():
            gen["mp4_url"] = resolve_url(gen.get("mp4_url"))
            gen["thumbnail_url"] = resolve_url(gen.get("thumbnail_url"))

    results = []
    for rid in page_record_ids:
        record = record_map.get(rid)
        if not record:
            continue
        results.append({
            "record": record,
            "generations": gen_map.get(rid, {}),
        })

    return {"results": results, "total": total, "page": page, "per_page": per_page}


@router.get("/{exp_id}/summary")
async def get_summary_route(exp_id: int):
    exp = get_experiment(exp_id)
    if not exp:
        raise HTTPException(404, "Experiment not found")
    return get_experiment_summary(exp_id)
