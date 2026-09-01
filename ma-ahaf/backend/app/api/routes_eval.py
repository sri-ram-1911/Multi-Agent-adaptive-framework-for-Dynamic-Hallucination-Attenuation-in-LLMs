"""Trigger + fetch evaluation runs (proposal §15, §16 Phase 5)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import Principal, requires
from app.core.errors import NotFound
from app.db import models
from app.db.session import get_db, session_scope
from app.eval.harness import run_evaluation

router = APIRouter(prefix="/v1/eval", tags=["evaluation"])


@router.post("/run", status_code=202)
def start_eval(
    background: BackgroundTasks,
    principal: Principal = Depends(requires("operator")),
    db: Session = Depends(get_db),
    dataset: str = "data/benchmark/benchmark.jsonl",
    limit: int = 40,
) -> dict:
    run = models.EvalRun(tenant_id=principal.tenant_id, dataset=dataset,
                         systems=["ma-ahaf", "static-rag"], status="running")
    db.add(run)
    db.flush()
    run_id = run.id

    def _job() -> None:
        with session_scope() as s:
            try:
                summary, pareto = run_evaluation(s, principal.tenant_id, dataset, limit=limit)
                r = s.get(models.EvalRun, run_id)
                r.status, r.summary, r.pareto = "done", summary, pareto
                from datetime import UTC, datetime

                r.finished_at = datetime.now(UTC)
            except Exception as exc:  # pragma: no cover
                r = s.get(models.EvalRun, run_id)
                r.status, r.summary = "failed", {"error": str(exc)}

    background.add_task(_job)
    return {"eval_run_id": run_id, "status": "running"}


@router.get("/runs")
def list_runs(
    principal: Principal = Depends(requires("viewer")),
    db: Session = Depends(get_db),
) -> list[dict]:
    rows = db.scalars(
        select(models.EvalRun).where(models.EvalRun.tenant_id == principal.tenant_id)
        .order_by(models.EvalRun.created_at.desc()).limit(25)
    ).all()
    return [
        {"id": r.id, "dataset": r.dataset, "status": r.status,
         "created_at": r.created_at.isoformat(), "summary": r.summary}
        for r in rows
    ]


@router.get("/runs/{run_id}")
def get_run(
    run_id: str,
    principal: Principal = Depends(requires("viewer")),
    db: Session = Depends(get_db),
) -> dict:
    r = db.get(models.EvalRun, run_id)
    if r is None or r.tenant_id != principal.tenant_id:
        raise NotFound("eval run not found")
    return {"id": r.id, "dataset": r.dataset, "status": r.status,
            "summary": r.summary, "pareto": r.pareto,
            "created_at": r.created_at.isoformat()}
