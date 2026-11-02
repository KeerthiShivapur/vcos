"""External Conflict Service — conflict detection, preservation, and resolution.

Implements:
- Conflict detection between external sources
- Conflict preservation (never destroy original observations)
- Multiple resolution paths (authority, manual, merge, superseded)
- Governed resolution through canonical mutation boundary
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict

from sqlalchemy import select, and_, or_, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    ExternalConflict,
    ExternalIdentityMapping,
    SourceAuthority,
    ConnectorInstance,
    CONFLICT_RESOLUTION_STATES,
    ENTITY_TYPES,
)

logger = logging.getLogger("vcos.integration.conflict")


class ExternalConflictService:
    """External conflict management service.
    
    Preserves all conflicts between external sources.
    Never destroys original conflicting observations.
    Provides multiple resolution paths with full provenance.
    """

    # ------------------------------------------------------------ Conflict Creation
    
    async def create_conflict(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        source_a_instance_id: str,
        source_a_external_id: str,
        source_a_value: Dict[str, Any],
        source_a_timestamp: datetime,
        source_b_instance_id: str,
        source_b_external_id: str,
        source_b_value: Dict[str, Any],
        source_b_timestamp: datetime,
        conflict_fields: List[str],
        detected_by_sync_run: Optional[str] = None,
        source_a_event_id: Optional[str] = None,
        source_b_event_id: Optional[str] = None,
    ) -> ExternalConflict:
        """Create a new external conflict record.
        
        Preserves both conflicting observations with full provenance.
        """
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Invalid entity type: {entity_type}")
        
        # Get authority precedence for both sources
        source_a_auth = await db.execute(
            select(SourceAuthority).where(
                SourceAuthority.organization_id == organization_id,
                SourceAuthority.entity_type == entity_type,
                SourceAuthority.connector_instance_id == source_a_instance_id,
            )
        )
        auth_a = source_a_auth.scalar_one_or_none()
        
        source_b_auth = await db.execute(
            select(SourceAuthority).where(
                SourceAuthority.organization_id == organization_id,
                SourceAuthority.entity_type == entity_type,
                SourceAuthority.connector_instance_id == source_b_instance_id,
            )
        )
        auth_b = source_b_auth.scalar_one_or_none()
        
        conflict = ExternalConflict(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            source_a_instance_id=source_a_instance_id,
            source_a_external_id=source_a_external_id,
            source_a_value=source_a_value,
            source_a_timestamp=source_a_timestamp,
            source_a_authority=auth_a.precedence if auth_a else 0,
            source_b_instance_id=source_b_instance_id,
            source_b_external_id=source_b_external_id,
            source_b_timestamp=source_b_timestamp,
            source_b_authority=auth_b.precedence if auth_b else 0,
            conflict_fields=list(set(source_a_value.keys()) & set(source_b_value.keys())),
            detected_at=utcnow(),
            detected_by_sync_run=detected_by_sync_run,
            source_a_event_id=source_a_event_id,
            source_b_event_id=source_b_event_id,
            resolution_state="open",
        )
        
        db.add(conflict)
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.detected",
            payload={
                "conflict_id": conflict.id,
                "organization_id": organization_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "source_a": source_a_instance_id,
                "source_b": source_b_instance_id,
                "conflict_fields": conflict.conflict_fields,
            },
        )
        
        return conflict

    async def detect_and_create_conflicts(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        entity_id: Optional[str] = None,
        source_values: Dict[str, Dict[str, Any]],  # connector_instance_id -> value dict
        timestamps: Dict[str, datetime],  # connector_instance_id -> timestamp
        external_ids: Dict[str, str],  # connector_instance_id -> external_id
        event_ids: Dict[str, Optional[str]] = None,  # connector_instance_id -> event_id
        sync_run_id: Optional[str] = None,
    ) -> List[ExternalConflict]:
        """Detect and create conflicts between multiple external sources.
        
        Compares all pairs of source values and creates conflicts for mismatches.
        """
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Invalid entity type: {entity_type}")
        
        conflicts = []
        source_items = list(source_values.items())
        
        for i in range(len(source_items)):
            for j in range(i + 1, len(source_items)):
                source_a_id, value_a = source_items[i]
                source_b_id, value_b = source_items[j]
                
                # Deep comparison of relevant fields
                conflict_fields = self._find_conflicting_fields(value_a, value_b)
                
                if conflict_fields:
                    conflict = await self.create_conflict(
                        db=db,
                        organization_id=organization_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        source_a_instance_id=source_a_id,
                        source_a_external_id=external_ids.get(source_a_id, ""),
                        source_a_value=value_a,
                        source_a_timestamp=timestamps.get(source_a_id, utcnow()),
                        source_b_instance_id=source_b_id,
                        source_b_external_id=external_ids.get(source_b_id, ""),
                        source_b_value=value_b,
                        source_b_timestamp=timestamps.get(source_b_id, utcnow()),
                        conflict_fields=conflict_fields,
                        detected_by_sync_run=sync_run_id,
                        source_a_event_id=event_ids.get(source_a_id) if event_ids else None,
                        source_b_event_id=event_ids.get(source_b_id) if event_ids else None,
                    )
                    conflicts.append(conflict)
        
        await db.flush()
        return conflicts

    def _find_conflicting_fields(self, value_a: Dict, value_b: Dict) -> List[str]:
        """Find fields that differ between two value dictionaries."""
        all_keys = set(value_a.keys()) | set(value_b.keys())
        conflicts = []
        
        for key in all_keys:
            val_a = value_a.get(key)
            val_b = value_b.get(key)
            
            if val_a != val_b:
                conflicts.append(key)
        
        return conflicts

    # ------------------------------------------------------------ Conflict Resolution
    
    async def resolve_by_authority(
        self,
        db: AsyncSession,
        *,
        conflict_id: str,
        organization_id: str,
        resolved_by: str,
        resolution_notes: Optional[str] = None,
    ) -> ExternalConflict:
        """Resolve conflict using configured source authority."""
        conflict = await db.get(ExternalConflict, conflict_id)
        if not conflict or conflict.organization_id != organization_id:
            raise ValueError("Conflict not found")
        
        if conflict.resolution_state != "open":
            raise ValueError(f"Conflict already resolved: {conflict.resolution_state}")
        
        # Get authority for both sources
        auth_a = await db.execute(
            select(SourceAuthority).where(
                SourceAuthority.organization_id == organization_id,
                SourceAuthority.entity_type == conflict.entity_type,
                SourceAuthority.connector_instance_id == conflict.source_a_instance_id,
            )
        )
        auth_a = auth_a.scalars().first()
        
        auth_b = await db.execute(
            select(SourceAuthority).where(
                SourceAuthority.organization_id == organization_id,
                SourceAuthority.entity_type == conflict.entity_type,
                SourceAuthority.connector_instance_id == conflict.source_b_instance_id,
            )
        )
        auth_b = auth_b.scalars().first()
        
        # Determine winner based on authority
        winner = None
        if auth_a and not auth_b:
            winner = "source_a"
        elif auth_b and not auth_a:
            winner = "source_b"
        elif auth_a and auth_b:
            if auth_a.precedence > auth_b.precedence:
                winner = "source_a"
            elif auth_b.precedence > auth_a.precedence:
                winner = "source_b"
            else:
                # Equal precedence — require manual resolution
                winner = None
        else:
            winner = None
        
        if not winner:
            # No clear authority winner — require manual
            conflict.resolution_state = "manual_resolution"
            conflict.resolution_method = "manual"
            conflict.resolution_notes = "Equal or missing authority — manual resolution required"
            conflict.resolved_by = resolved_by
            conflict.resolved_at = utcnow()
            conflict.resolution_notes = "Equal or missing source authority"
        else:
            conflict.resolution_state = "authority_applied"
            conflict.resolution_method = "authority"
            conflict.resolved_value = conflict.source_a_value if winner == "source_a" else conflict.source_b_value
            conflict.resolved_by = resolved_by
            conflict.resolved_at = utcnow()
            conflict.resolution_notes = f"Authority applied: {winner} ({resolution_notes or ''})"
        
        conflict.updated_at = utcnow()
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.authority_applied",
            payload={
                "conflict_id": conflict.id,
                "winner": winner,
                "resolved_by": resolved_by,
            },
        )
        
        return conflict

    async def resolve_manually(
        self,
        db: AsyncSession,
        *,
        conflict_id: str,
        organization_id: str,
        resolved_by: str,
        resolved_value: Dict[str, Any],
        resolution_notes: Optional[str] = None,
    ) -> ExternalConflict:
        """Manually resolve a conflict with an explicit value."""
        conflict = await db.get(ExternalConflict, conflict_id)
        if not conflict or conflict.organization_id != organization_id:
            raise ValueError("Conflict not found")
        
        if conflict.resolution_state != "open":
            raise ValueError(f"Conflict already resolved: {conflict.resolution_state}")
        
        conflict.resolution_state = "manual_resolution"
        conflict.resolution_method = "manual"
        conflict.resolved_value = resolved_value
        conflict.resolved_by = resolved_by
        conflict.resolved_at = utcnow()
        conflict.resolution_notes = resolution_notes
        conflict.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.manually_resolved",
            payload={"conflict_id": conflict.id, "resolved_by": resolved_by},
        )
        
        return conflict

    async def merge_conflict(
        self,
        db: AsyncSession,
        *,
        conflict_id: str,
        organization_id: str,
        resolved_by: str,
        merged_value: Dict[str, Any],
        resolution_notes: Optional[str] = None,
    ) -> ExternalConflict:
        """Merge conflicting values into a combined value."""
        conflict = await db.get(ExternalConflict, conflict_id)
        if not conflict or conflict.organization_id != organization_id:
            raise ValueError("Conflict not found")
        
        if conflict.resolution_state != "open":
            raise ValueError(f"Conflict already resolved: {conflict.resolution_state}")
        
        conflict.resolution_state = "merged"
        conflict.resolution_method = "merged"
        conflict.resolved_value = merged_value
        conflict.resolved_by = resolved_by
        conflict.resolved_at = utcnow()
        conflict.resolution_notes = resolution_notes or "Merged conflicting values"
        conflict.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.merged",
            payload={"conflict_id": conflict.id, "merged_by": resolved_by},
        )
        
        return conflict

    async def supersede_conflict(
        self,
        db: AsyncSession,
        *,
        conflict_id: str,
        organization_id: str,
        resolved_by: str,
        superseding_value: Dict[str, Any],
        resolution_notes: Optional[str] = None,
    ) -> ExternalConflict:
        """Mark conflict as superseded by a newer observation."""
        conflict = await db.get(ExternalConflict, conflict_id)
        if not conflict or conflict.organization_id != organization_id:
            raise ValueError("Conflict not found")
        
        if conflict.resolution_state != "open":
            raise ValueError(f"Conflict already resolved: {conflict.resolution_state}")
        
        conflict.resolution_state = "superseded"
        conflict.resolution_method = "superseded"
        conflict.resolved_value = superseding_value
        conflict.resolved_by = resolved_by
        conflict.resolved_at = utcnow()
        conflict.resolution_notes = resolution_notes or "Superseded by newer observation"
        conflict.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.superseded",
            payload={"conflict_id": conflict.id, "superseded_by": resolved_by},
        )
        
        return conflict

    # ------------------------------------------------------------ Conflict Queries
    
    async def get_conflicts(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        state: Optional[str] = "open",
        connector_instance_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ExternalConflict]:
        """Query conflicts with filters."""
        query = select(ExternalConflict).where(
            ExternalConflict.organization_id == organization_id
        )
        
        if entity_type:
            query = query.where(ExternalConflict.entity_type == entity_type)
        if entity_id:
            query = query.where(ExternalConflict.entity_id == entity_id)
        if state:
            query = query.where(ExternalConflict.resolution_state == state)
        if connector_instance_id:
            query = query.where(
                or_(
                    ExternalConflict.source_a_instance_id == connector_instance_id,
                    ExternalConflict.source_b_instance_id == connector_instance_id,
                )
            )
        
        query = query.order_by(desc(ExternalConflict.detected_at)).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_open_conflicts(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        entity_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[ExternalConflict]:
        """Get all open conflicts for an organization."""
        return await self.get_conflicts(
            db, organization_id, entity_type=entity_type, state="open", limit=limit
        )

    async def get_conflicts_for_entity(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
        entity_id: str,
    ) -> List[ExternalConflict]:
        """Get all conflicts (open and resolved) for a specific entity."""
        return await self.get_conflicts(
            db, organization_id, entity_type=entity_type, entity_id=entity_id, state=None, limit=1000
        )

    async def get_conflicts_by_connector(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: str,
        *,
        state: Optional[str] = "open",
        limit: int = 100,
    ) -> List[ExternalConflict]:
        """Get conflicts involving a specific connector instance."""
        return await self.get_conflicts(
            db, organization_id, connector_instance_id=connector_instance_id, state=state, limit=limit
        )

    # ------------------------------------------------------------ Conflict Statistics
    
    async def get_conflict_stats(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Get conflict statistics for an organization."""
        result = await db.execute(
            select(
                ExternalConflict.resolution_state,
                func.count(ExternalConflict.id)
            ).where(
                ExternalConflict.organization_id == organization_id
            ).group_by(ExternalConflict.resolution_state)
        )
        
        state_counts = {row[0]: row[1] for row in result.all()}
        
        total = sum(state_counts.values())
        open_count = state_counts.get("open", 0)
        resolved_count = sum(v for k, v in state_counts.items() if k != "open")
        
        # Conflicts by entity type
        type_result = await db.execute(
            select(ExternalConflict.entity_type, func.count(ExternalConflict.id))
            .where(ExternalConflict.organization_id == organization_id)
            .group_by(ExternalConflict.entity_type)
        )
        by_type = {row[0]: row[1] for row in type_result.all()}
        
        # Conflicts by resolution method
        method_result = await db.execute(
            select(ExternalConflict.resolution_method, func.count(ExternalConflict.id))
            .where(ExternalConflict.organization_id == organization_id)
            .group_by(ExternalConflict.resolution_method)
        )
        by_method = {row[0]: row[1] for row in method_result.all() if row[0]}
        
        return {
            "total": total,
            "open": open_count,
            "resolved": resolved_count,
            "by_state": state_counts,
            "by_entity_type": by_type,
            "by_resolution_method": by_method,
        }


# Global instance
external_conflict_service = ExternalConflictService()