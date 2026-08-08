from __future__ import annotations

"""Developer certification service (Phase 18.19) â€” exams & credentials.

Developers earn certification credentials (plugin-developer, solution-
architect, professional, partner) by passing a score threshold; credentials
expire after one year and are revoked by admins.
"""

from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.developer import CertificationCredential

EXAMS = {
    "plugin-developer": {"badge": "VCOS Certified Plugin Developer", "pass_score": 70.0},
    "solution-architect": {"badge": "VCOS Certified Solution Architect", "pass_score": 75.0},
    "professional": {"badge": "VCOS Professional Developer", "pass_score": 80.0},
    "partner": {"badge": "VCOS Certified Partner", "pass_score": 85.0},
}
VALIDITY_DAYS = 365


class CertificationService:
    async def attempt(
        self,
        db: AsyncSession,
        *,
        developer_id: str,
        exam: str,
        score: float,
        organization_id: Optional[str] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if exam not in EXAMS:
            raise ValueError(f"exam must be one of {list(EXAMS)}")
        passed = score >= EXAMS[exam]["pass_score"]
        now = utcnow()
        row = CertificationCredential(
            developer_id=developer_id,
            exam=exam,
            status="passed" if passed else "failed",
            score=score,
            badge=EXAMS[exam]["badge"] if passed else "",
            issued_at=now,
            expires_at=(now + timedelta(days=VALIDITY_DAYS)) if passed else None,
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="certification.issued" if passed else "certification.attempted",
            organization_id=organization_id or developer_id,
            payload={"exam": exam, "score": score, "passed": passed},
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    async def credentials(
        self, db: AsyncSession, developer_id: str, status: Optional[str] = None
    ) -> list[dict[str, Any]]:
        stmt = select(CertificationCredential).where(CertificationCredential.developer_id == developer_id)
        if status:
            stmt = stmt.where(CertificationCredential.status == status)
        rows = (
            await db.execute(stmt.order_by(CertificationCredential.issued_at.desc()))
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def revoke(self, db: AsyncSession, developer_id: str, credential_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(CertificationCredential).where(
                    CertificationCredential.developer_id == developer_id,
                    CertificationCredential.id == credential_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = "revoked"
        await db.flush()
        return self.serialize(row)

    def serialize(self, row: CertificationCredential) -> dict[str, Any]:
        return {
            "id": row.id,
            "developer_id": row.developer_id,
            "exam": row.exam,
            "status": row.status,
            "score": row.score,
            "badge": row.badge,
            "issued_at": row.issued_at.isoformat() if row.issued_at else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


certification_service = CertificationService()
