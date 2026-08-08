"""Cloud regions & multi-region deployment (Phase 16.3)."""

import math
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.infrastructure import CloudRegion, RegionStatus
from app.models.organization import gen_uuid

DEFAULT_REGIONS: list[dict[str, Any]] = [
    {"name": "asia-mumbai", "provider": "aws", "location": "Mumbai, India", "continent": "asia", "latency_ms": 5},
    {"name": "asia-singapore", "provider": "aws", "location": "Singapore", "continent": "asia", "latency_ms": 40},
    {"name": "europe-frankfurt", "provider": "aws", "location": "Frankfurt, Germany", "continent": "europe", "latency_ms": 15},
    {"name": "europe-london", "provider": "aws", "location": "London, UK", "continent": "europe", "latency_ms": 35},
    {"name": "na-virginia", "provider": "aws", "location": "Virginia, USA", "continent": "north_america", "latency_ms": 10},
    {"name": "na-oregon", "provider": "aws", "location": "Oregon, USA", "continent": "north_america", "latency_ms": 60},
    {"name": "sa-saopaulo", "provider": "aws", "location": "Sao Paulo, Brazil", "continent": "south_america", "latency_ms": 25},
    {"name": "africa-capetown", "provider": "aws", "location": "Cape Town, South Africa", "continent": "africa", "latency_ms": 45},
    {"name": "oc-sydney", "provider": "aws", "location": "Sydney, Australia", "continent": "australia", "latency_ms": 20},
    {"name": "me-bahrain", "provider": "aws", "location": "Bahrain", "continent": "middle_east", "latency_ms": 50},
]


def _region_status(status: str) -> str:
    """Map CloudRegion status (active|degraded|offline|maintenance) to RegionStatus (healthy|degraded|offline)."""
    return {"active": "healthy", "maintenance": "degraded"}.get(status, status)


class RegionsService:
    """Multi-region topology: CRUD, nearest-region routing, residency."""

    async def list_regions(self, db: AsyncSession, status: Optional[str] = None) -> list[CloudRegion]:
        query = select(CloudRegion)
        if status:
            query = query.where(CloudRegion.status == status)
        result = await db.execute(query.order_by(CloudRegion.name))
        return list(result.scalars().all())

    async def get_region(self, db: AsyncSession, region_id: str) -> Optional[CloudRegion]:
        return await db.get(CloudRegion, region_id)

    async def get_region_by_name(self, db: AsyncSession, name: str) -> Optional[CloudRegion]:
        result = await db.execute(select(CloudRegion).where(CloudRegion.name == name))
        return result.scalars().first()

    async def create_region(self, db: AsyncSession, **payload: Any) -> CloudRegion:
        name = str(payload.get("name", "")).strip()
        if not name:
            raise ValueError("Region name is required")
        existing = await self.get_region_by_name(db, name)
        if existing is not None:
            raise ValueError(f"Region '{name}' already exists")
        region = CloudRegion(
            id=gen_uuid(),
            name=name,
            provider=str(payload.get("provider", "aws")),
            location=payload.get("location"),
            continent=str(payload.get("continent", "north_america")),
            status=str(payload.get("status", "active")),
            latency_ms=int(payload.get("latency_ms", 0) or 0),
            load_percent=int(payload.get("load_percent", 0) or 0),
            residency=payload.get("residency") or [],
            endpoints=payload.get("endpoints") or {},
            active_instances=int(payload.get("active_instances", 1) or 1),
        )
        db.add(region)
        await db.flush()
        await self.upsert_region_status(
            db,
            region=region.name,
            service="api",
            status=_region_status(region.status),
            active_instances=region.active_instances,
            latency_ms=region.latency_ms,
            load_percent=region.load_percent,
        )
        return region

    async def update_region(self, db: AsyncSession, region_id: str, **payload: Any) -> Optional[CloudRegion]:
        region = await self.get_region(db, region_id)
        if region is None:
            return None
        for key, value in payload.items():
            if value is not None and hasattr(region, key):
                setattr(region, key, value)
        await db.flush()
        if "status" in payload or "load_percent" in payload or "latency_ms" in payload:
            await self.upsert_region_status(
                db,
                region=region.name,
                service="api",
                status=_region_status(region.status),
                active_instances=region.active_instances,
                latency_ms=region.latency_ms,
                load_percent=region.load_percent,
            )
        return region

    async def delete_region(self, db: AsyncSession, region_id: str) -> bool:
        region = await self.get_region(db, region_id)
        if region is None:
            return False
        result = await db.execute(select(RegionStatus).where(RegionStatus.region == region.name))
        for row in result.scalars().all():
            await db.delete(row)
        await db.delete(region)
        await db.flush()
        return True

    async def upsert_region_status(
        self,
        db: AsyncSession,
        *,
        region: str,
        service: str,
        status: str,
        active_instances: int = 0,
        degraded_instances: int = 0,
        offline_instances: int = 0,
        latency_ms: int = 0,
        load_percent: int = 0,
    ) -> RegionStatus:
        result = await db.execute(
            select(RegionStatus).where(RegionStatus.region == region, RegionStatus.service == service)
        )
        row = result.scalars().first()
        if row is None:
            row = RegionStatus(
                id=gen_uuid(), region=region, service=service, status=status,
                active_instances=active_instances, degraded_instances=degraded_instances,
                offline_instances=offline_instances, latency_ms=latency_ms, load_percent=load_percent,
            )
            db.add(row)
        else:
            row.status = status
            row.active_instances = active_instances
            row.degraded_instances = degraded_instances
            row.offline_instances = offline_instances
            row.latency_ms = latency_ms
            row.load_percent = load_percent
        from app.core.timeutils import utcnow

        row.last_checked_at = utcnow()
        await db.flush()
        return row

    async def nearest_region(
        self, db: AsyncSession, *, ip: Optional[str] = None, latency: Optional[int] = None, continent: Optional[str] = None
    ) -> dict[str, Any]:
        """Route the caller to the nearest healthy region."""
        regions = await self.list_regions(db, status="active")
        if not regions:
            return {"region": None, "reason": "no healthy regions"}
        score: list[tuple[float, CloudRegion]] = []
        for region in regions:
            s = float(region.latency_ms)
            if continent and region.continent == continent:
                s *= 0.2
            if ip:
                s *= 1.0 + (hash(ip) % 100) / 1000.0
            score.append((s, region))
        score.sort(key=lambda pair: pair[0])
        best = score[0][1]
        return {
            "region": best.name,
            "location": best.location,
            "continent": best.continent,
            "latency_ms": best.latency_ms,
            "load_percent": best.load_percent,
            "provider": best.provider,
        }

    async def summary(self, db: AsyncSession) -> dict[str, Any]:
        regions = await self.list_regions(db)
        by_status: dict[str, int] = {}
        total_instances = 0
        for region in regions:
            by_status[region.status] = by_status.get(region.status, 0) + 1
            total_instances += region.active_instances + region.degraded_instances + region.offline_instances
        return {
            "regions": len(regions),
            "by_status": by_status,
            "total_instances": total_instances,
            "healthy_percent": round(
                100 * by_status.get("active", 0) / max(1, len(regions)), 1
            ),
            "continents": sorted({region.continent for region in regions}),
        }

    async def residency_check(self, db: AsyncSession, region_id: str, compliance: str) -> dict[str, Any]:
        region = await self.get_region(db, region_id)
        if region is None:
            return {"allowed": False, "reason": "unknown region"}
        allowed = compliance in (region.residency or []) or not region.residency
        return {
            "allowed": allowed,
            "region": region.name,
            "compliance": compliance,
            "residency": region.residency,
        }

    async def canary_regions(self, db: AsyncSession) -> list[dict[str, Any]]:
        """Pick candidate failover regions per active region (capacity math)."""
        regions = await self.list_regions(db, status="active")
        candidates: list[dict[str, Any]] = []
        for region in regions:
            headroom = max(0, 100 - region.load_percent)
            capacity = math.floor(headroom / max(1, region.load_percent) * 10) if region.load_percent else 100
            candidates.append(
                {
                    "region": region.name,
                    "load_percent": region.load_percent,
                    "headroom_percent": headroom,
                    "estimated_absorbs": capacity,
                }
            )
        return sorted(candidates, key=lambda c: c["load_percent"])


regions_service = RegionsService()
