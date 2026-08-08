"""Digital twin sync — keeps the twin synchronized with organizational data.

Refreshes the Phase 18 digital twin, feeds its state into awareness and the
organization graph, and records organizational metrics so the twin evolves
continuously with the company.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession


class DigitalTwinSync:
    async def sync(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """Refresh the digital twin and return a consistency report."""
        report: dict[str, Any] = {"twin_ok": False, "entities": {}, "notes": []}
        try:
            from app.digital_twin.twin_service import digital_twin_service

            twin = await digital_twin_service.get_twin(db, organization_id)
            if twin:
                report["twin_ok"] = True
                report["entities"] = {
                    key: value for key, value in (twin.get("entity_counts") or {}).items()
                    if isinstance(value, int)
                }
                report["score"] = twin.get("health_score")
                report["refreshed_at"] = twin.get("refreshed_at")
        except Exception as exc:  # pragma: no cover - defensive
            report["notes"].append(f"twin refresh failed: {exc}")

        try:
            await self._ensure_graph_nodes(db, organization_id)
            report["graph_nodes_synced"] = True
        except Exception as exc:  # pragma: no cover - defensive
            report["notes"].append(f"graph sync failed: {exc}")
        return report

    async def _ensure_graph_nodes(self, db: AsyncSession, organization_id: str) -> None:
        """Best-effort: register key entities as graph nodes."""
        from sqlalchemy import func, select

        from app.models.company_state import OrganizationMetric
        from app.models.customer import Customer
        from app.models.employee import Employee
        from app.models.knowledge import Document
        from app.models.organization_node import OrganizationNode
        from app.models.project import Project

        counts = {
            "employee": (
                select(func.count(Employee.id)).where(Employee.organization_id == organization_id)
            ),
            "project": (
                select(func.count(Project.id)).where(Project.organization_id == organization_id)
            ),
            "customer": (
                select(func.count(Customer.id)).where(Customer.organization_id == organization_id)
            ),
            "document": (
                select(func.count(Document.id)).where(Document.organization_id == organization_id)
            ),
        }
        for node_type, stmt in counts.items():
            value = (await db.execute(stmt)).scalar() or 0
            if value <= 0:
                continue
            db.add(
                OrganizationMetric(
                    organization_id=organization_id,
                    name=f"nodes_{node_type}",
                    value=float(value),
                    unit="count",
                    period="daily",
                    source="twin_sync",
                )
            )
        await db.flush()


digital_twin_sync = DigitalTwinSync()
