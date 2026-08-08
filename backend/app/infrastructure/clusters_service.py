"""Replicated cluster health: primary/replica failover (Phase 16.5)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.infrastructure import ClusterStatus
from app.models.organization import gen_uuid

CLUSTER_TYPES = ("postgres", "redis", "neo4j", "opensearch", "ai", "gateway", "object_storage", "queue", "search", "graph")
ROLE_PRIMARY = "primary"
ROLE_REPLICA = "replica"
CLUSTER_STATUSES = ("healthy", "degraded", "offline", "recovering")


class ClustersService:
    """Track nodes per cluster type and execute failover decisions."""

    async def list_clusters(
        self, db: AsyncSession, *, cluster_type: Optional[str] = None, status: Optional[str] = None
    ) -> list[ClusterStatus]:
        query = select(ClusterStatus)
        if cluster_type:
            query = query.where(ClusterStatus.cluster_type == cluster_type)
        if status:
            query = query.where(ClusterStatus.status == status)
        result = await db.execute(query.order_by(ClusterStatus.region, ClusterStatus.cluster_type))
        return list(result.scalars().all())

    async def get_cluster(self, db: AsyncSession, cluster_id: str) -> Optional[ClusterStatus]:
        return await db.get(ClusterStatus, cluster_id)

    async def upsert_node(
        self,
        db: AsyncSession,
        *,
        cluster_type: str,
        region: Optional[str] = None,
        name: Optional[str] = None,
        role: str = ROLE_REPLICA,
        status: str = "healthy",
        version: Optional[str] = None,
        lag_seconds: int = 0,
        healthy_nodes: int = 1,
        total_nodes: int = 1,
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> ClusterStatus:
        if cluster_type not in CLUSTER_TYPES:
            raise ValueError(f"Unknown cluster type '{cluster_type}', expected one of {', '.join(CLUSTER_TYPES)}")
        if role not in (ROLE_PRIMARY, ROLE_REPLICA):
            raise ValueError("role must be primary or replica")
        if status not in CLUSTER_STATUSES:
            raise ValueError(f"status must be one of {', '.join(CLUSTER_STATUSES)}")
        node_name = name or f"{cluster_type}-{role}"
        result = await db.execute(
            select(ClusterStatus).where(
                ClusterStatus.cluster_type == cluster_type,
                ClusterStatus.region == region,
                ClusterStatus.name == node_name,
            )
        )
        node = result.scalars().first()
        if node is None:
            node = ClusterStatus(
                id=gen_uuid(),
                cluster_type=cluster_type,
                region=region,
                name=node_name,
                role=role,
                status=status,
                version=version,
                lag_seconds=lag_seconds,
                healthy_nodes=healthy_nodes,
                total_nodes=total_nodes,
                last_checked_at=utcnow(),
            )
            db.add(node)
        else:
            node.status = status
            node.role = role
            node.version = version or node.version
            node.lag_seconds = lag_seconds
            node.healthy_nodes = healthy_nodes
            node.total_nodes = total_nodes
            node.last_checked_at = utcnow()
        await db.flush()
        return node

    async def node_failure(self, db: AsyncSession, *, cluster_id: str, organization_id: Optional[str] = None, actor_id: Optional[str] = None) -> Optional[ClusterStatus]:
        node = await self.get_cluster(db, cluster_id)
        if node is None:
            return None
        node.status = "degraded"
        node.healthy_nodes = max(0, node.healthy_nodes - 1)
        node.last_checked_at = utcnow()
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="replica.failed",
            actor_id=actor_id,
            payload={"node_id": node.id, "cluster_type": node.cluster_type, "name": node.name, "role": node.role},
        )
        return node

    async def failover(self, db: AsyncSession, *, cluster_type: str, region: Optional[str] = None, organization_id: Optional[str] = None, actor_id: Optional[str] = None) -> dict[str, Any]:
        """Promote the healthiest replica to primary when the primary is down."""
        nodes = await self.list_clusters(db, cluster_type=cluster_type)
        if region:
            nodes = [node for node in nodes if node.region == region]
        primary = next((node for node in nodes if node.role == ROLE_PRIMARY), None)
        replicas = [node for node in nodes if node.role == ROLE_REPLICA]
        if primary is None:
            return {"failover": False, "reason": f"no primary registered for {cluster_type}"}
        if primary.status == "healthy":
            return {"failover": False, "reason": "primary is healthy", "primary": primary.name}
        healthy_replicas = [
            node for node in replicas if node.status == "healthy" and node.healthy_nodes == node.total_nodes
        ]
        if not healthy_replicas:
            healthy_replicas = [node for node in replicas if node.status in ("healthy", "recovering")]
        if not healthy_replicas:
            return {"failover": False, "reason": "no healthy replica available"}
        new_primary = healthy_replicas[0]
        primary.status = "offline"
        new_primary.role = ROLE_PRIMARY
        new_primary.status = "healthy"
        new_primary.last_checked_at = utcnow()
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="cluster.recovered",
            actor_id=actor_id,
            payload={
                "cluster_type": cluster_type,
                "old_primary": primary.name,
                "new_primary": new_primary.name,
                "region": new_primary.region,
            },
        )
        return {
            "failover": True,
            "cluster_type": cluster_type,
            "old_primary": primary.name,
            "new_primary": new_primary.name,
            "region": new_primary.region,
        }

    async def topology(self, db: AsyncSession, cluster_type: str) -> dict[str, Any]:
        nodes = await self.list_clusters(db, cluster_type=cluster_type)
        return {
            "cluster_type": cluster_type,
            "nodes": len(nodes),
            "primaries": sum(1 for node in nodes if node.role == ROLE_PRIMARY),
            "replicas": sum(1 for node in nodes if node.role == ROLE_REPLICA),
            "healthy": sum(1 for node in nodes if node.status == "healthy"),
            "degraded": sum(1 for node in nodes if node.status == "degraded"),
            "offline": sum(1 for node in nodes if node.status == "offline"),
            "topology": [
                {
                    "node_id": node.id,
                    "name": node.name,
                    "region": node.region,
                    "role": node.role,
                    "status": node.status,
                    "version": node.version,
                    "healthy_nodes": node.healthy_nodes,
                    "total_nodes": node.total_nodes,
                    "lag_seconds": node.lag_seconds,
                }
                for node in nodes
            ],
        }


clusters_service = ClustersService()
