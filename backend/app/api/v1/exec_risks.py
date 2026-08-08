"""Phase 8.4 — Strategic Risk API."""

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.executive.risk_engine import risk_engine
from app.models.executive import StrategicRisk
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/executive/risks", tags=["executive"])


def _payload(r: StrategicRisk) -> dict[str, Any]:
    def _load(v: Optional[str]) -> Any:
        if not v:
            return []
        try:
            return json.loads(v)
        except (json.JSONDecodeError, TypeError):
            return []

    return {
        "id": r.id,
        "kind": r.kind,
        "title": r.title,
        "description": r.description,
        "probability": r.probability,
        "impact": r.impact,
        "score": r.score,
        "level": r.level,
        "subject_type": r.subject_type,
        "subject_id": r.subject_id,
        "subject_name": r.subject_name,
        "affected_teams": _load(r.affected_teams_json),
        "recommended_actions": _load(r.recommended_actions_json),
        "evidence": _load(r.evidence_json),
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("")
async def list_risks(
    refresh: bool = False,
    level: Optional[str] = Query(default=None, pattern="^(low|medium|high|critical)$"),
    status: Optional[str] = Query(default=None, pattern="^(open|accepted|mitigated)$"),
    limit: int = Query(default=50, ge=1, le=200),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if refresh:
        risks = await risk_engine.detect_all(db, organization_id=org.id)
        await risk_engine.persist(db, organization_id=org.id, risks=risks)
        await db.commit()
    query = select(StrategicRisk).where(StrategicRisk.organization_id == org.id)
    if level:
        query = query.where(StrategicRisk.level == level)
    if status:
        query = query.where(StrategicRisk.status == status)
    rows = (await db.execute(query.order_by(StrategicRisk.score.desc()).limit(limit))).scalars().all()
    return {"total": len(rows), "risks": [_payload(r) for r in rows]}


@router.get("/{risk_id}")
async def get_risk(
    risk_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:view")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    risk = await db.get(StrategicRisk, risk_id)
    if risk is None or risk.organization_id != org.id:
        raise HTTPException(404, "Strategic risk not found")
    return _payload(risk)


class RiskStatusIn(BaseModel):
    status: str  # open | accepted | mitigated


@router.patch("/{risk_id}/status")
async def update_risk_status(
    risk_id: str,
    payload: RiskStatusIn,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("executive:manage")),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    risk = await db.get(StrategicRisk, risk_id)
    if risk is None or risk.organization_id != org.id:
        raise HTTPException(404, "Strategic risk not found")
    if payload.status not in ("open", "accepted", "mitigated"):
        raise HTTPException(422, "status must be open|accepted|mitigated")
    risk.status = payload.status
    await db.commit()
    return {"id": risk.id, "status": risk.status}
