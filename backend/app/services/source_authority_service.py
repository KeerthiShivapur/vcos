"""Source Authority Service — governed source precedence for entity domains.

Implements:
- Source authority configuration per entity domain
- Authority resolution when sources disagree
- Governed authority application (no silent overwrites)
- Conflict preservation through ExternalConflict
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict, Tuple

from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    SourceAuthority,
    ExternalConflict,
    ExternalIdentityMapping,
    ConnectorInstance,
    CONFLICT_RESOLUTION_STATES,
    SOURCE_AUTHORITY_LEVELS,
    ENTITY_TYPES,
)

logger = logging.getLogger("vcos.integration.authority")


class SourceAuthorityService:
    """Source authority resolution service.
    
    Different external systems are authoritative for different domains.
    This service manages governed source precedence and applies it during
    conflict resolution without silent overwrites.
    """

    # ------------------------------------------------------------ Authority Configuration
    
    async def configure_authority(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        connector_instance_id: str,
        authority_level: str,
        precedence: int = 0,
        field_scope: Optional[List[str]] = None,
        conditions: Optional[Dict] = None,
        configured_by: str,
        approved_by: Optional[str] = None,
    ) -> SourceAuthority:
        """Configure source authority for an entity domain.
        
        Different systems are authoritative for different domains.
        e.g., HR system → employment data (primary), GitHub → code/repos (primary)
        """
        if entity_type not in ENTITY_TYPES:
            raise ValueError(f"Invalid entity type: {entity_type}")
        
        if authority_level not in SOURCE_AUTHORITY_LEVELS:
            raise ValueError(f"Invalid authority level: {authority_level}")
        
        # Verify connector instance exists
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if not instance or instance.organization_id != organization_id:
            raise ValueError("Invalid connector instance")
        
        # Check for existing authority
        existing = await db.execute(
            select(SourceAuthority).where(
                SourceAuthority.organization_id == organization_id,
                SourceAuthority.entity_type == entity_type,
                SourceAuthority.connector_instance_id == connector_instance_id,
            )
        )
        authority = existing.scalar_one_or_none()
        
        if authority:
            # Update existing
            authority.authority_level = authority_level
            authority.precedence = precedence
            authority.field_scope = field_scope or []
            authority.conditions = conditions
            authority.configured_by = configured_by
            if approved_by:
                authority.approved_by = approved_by
                authority.approved_at = utcnow()
            authority.updated_at = utcnow()
        else:
            authority = SourceAuthority(
                organization_id=organization_id,
                entity_type=entity_type,
                connector_instance_id=connector_instance_id,
                authority_level=authority_level,
                precedence=precedence,
                field_scope=field_scope or [],
                conditions=conditions,
                configured_by=configured_by,
                approved_by=approved_by,
                approved_at=utcnow() if approved_by else None,
            )
            db.add(authority)
        
        await db.flush()
        
        await publish_event(
            db,
            name="source_authority.configured",
            organization_id=organization_id,
            payload={
                "authority_id": authority.id,
                "entity_type": entity_type,
                "connector_instance_id": connector_instance_id,
                "authority_level": authority_level,
                "precedence": precedence,
            },
        )
        
        return authority

    async def get_authorities(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        entity_type: Optional[str] = None,
    ) -> List[SourceAuthority]:
        """Get all configured source authorities for an organization."""
        query = select(SourceAuthority).where(
            SourceAuthority.organization_id == organization_id
        )
        
        if entity_type:
            query = query.where(SourceAuthority.entity_type == entity_type)
        
        query = query.order_by(SourceAuthority.entity_type, desc(SourceAuthority.precedence))
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_authority_for_domain(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
    ) -> List[SourceAuthority]:
        """Get all authorities for a specific entity domain, ordered by precedence."""
        result = await db.execute(
            select(SourceAuthority).where(
                SourceAuthority.organization_id == organization_id,
                SourceAuthority.entity_type == entity_type,
            ).order_by(desc(SourceAuthority.precedence))
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------ Authority Resolution
    
    async def resolve_authority(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
        source_instances: List[Tuple[str, int]],  # (connector_instance_id, authority_precedence)
    ) -> Optional[SourceAuthority]:
        """Resolve the highest authority source for a domain among given sources.
        
        Returns the SourceAuthority with highest precedence among the sources.
        """
        if not source_instances:
            return None
        
        # Get all authorities for this domain
        authorities = await self.get_authority_for_domain(db, organization_id, entity_type)
        
        # Filter to only the sources we're considering
        source_ids = {si[0] for si in source_instances}
        relevant = [a for a in authorities if a.connector_instance_id in source_ids]
        
        if not relevant:
            # No configured authority for these sources — return highest precedence among them
            return None
        
        # Return highest precedence
        return max(relevant, key=lambda a: a.precedence)

    async def get_primary_authority(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
    ) -> Optional[SourceAuthority]:
        """Get the primary (highest precedence) authority for a domain."""
        authorities = await self.get_authority_for_domain(db, organization_id, entity_type)
        primary = [a for a in authorities if a.authority_level == "primary"]
        if primary:
            return max(primary, key=lambda a: a.precedence)
        # Fall back to highest precedence
        return max(authorities, key=lambda a: a.precedence) if authorities else None

    # ------------------------------------------------------------ Conflict Resolution
    
    async def apply_authority_to_conflict(
        self,
        db: AsyncSession,
        *,
        conflict_id: str,
        organization_id: str,
        resolved_by: str,
        resolution_method: str = "authority",
        resolution_notes: Optional[str] = None,
    ) -> ExternalConflict:
        """Apply source authority to resolve a conflict.
        
        Uses configured source authority to determine the winning value.
        Creates ExternalConflict record with resolution.
        """
        conflict = await db.get(ExternalConflict, conflict_id)
        if not conflict or conflict.organization_id != organization_id:
            raise ValueError("Conflict not found")
        
        if conflict.resolution_state != "open":
            raise ValueError(f"Conflict already resolved: {conflict.resolution_state}")
        
        # Get primary authority for this entity type
        primary_auth = await self.get_primary_authority(db, organization_id, conflict.entity_type)
        
        if not primary_auth:
            # No configured authority — require manual resolution
            conflict.resolution_state = "manual_resolution"
            conflict.resolved_by = resolved_by
            conflict.resolved_at = utcnow()
            conflict.resolution_method = "manual"
            conflict.resolution_notes = resolution_notes or "No configured source authority"
            conflict.updated_at = utcnow()
            await db.flush()
            return conflict
        
        # Determine winner based on authority
        source_a_is_primary = conflict.source_a_instance_id == primary_auth.connector_instance_id
        source_b_is_primary = conflict.source_b_instance_id == primary_auth.connector_instance_id
        
        if source_a_is_primary and not source_b_is_primary:
            resolved_value = conflict.source_a_value
            winner = "source_a"
        elif source_b_is_primary and not source_a_is_primary:
            resolved_value = conflict.source_b_value
            winner = "source_b"
        elif source_a_is_primary and source_b_is_primary:
            # Both primary — use higher precedence
            if conflict.source_a_authority >= conflict.source_b_authority:
                resolved_value = conflict.source_a_value
                winner = "source_a"
            else:
                resolved_value = conflict.source_b_value
                winner = "source_b"
        else:
            # Neither primary — use higher precedence
            if conflict.source_a_authority >= conflict.source_b_authority:
                resolved_value = conflict.source_a_value
                winner = "source_a"
            else:
                resolved_value = conflict.source_b_value
                winner = "source_b"
        
        # Record resolution
        conflict.resolution_state = "authority_applied"
        conflict.resolution_method = "authority"
        conflict.resolved_value = resolved_value
        conflict.resolved_by = resolved_by
        conflict.resolved_at = utcnow()
        conflict.resolution_notes = resolution_notes or f"Authority applied: {winner} (instance {primary_auth.connector_instance_id})"
        conflict.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.authority_applied",
            payload={
                "conflict_id": conflict.id,
                "entity_type": conflict.entity_type,
                "winner": winner,
                "primary_authority": primary_auth.connector_instance_id,
            },
        )
        
        return conflict

    async def manual_resolve_conflict(
        self,
        db: AsyncSession,
        *,
        conflict_id: str,
        organization_id: str,
        resolved_by: str,
        resolved_value: Dict[str, Any],
        resolution_notes: Optional[str] = None,
    ) -> ExternalConflict:
        """Manually resolve a conflict with explicit value."""
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

    # ------------------------------------------------------------ Conflict Detection
    
    async def detect_conflicts(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
        entity_id: str,
        source_values: Dict[str, Dict[str, Any]],  # connector_instance_id -> value
        *,
        external_ids: Optional[Dict[str, str]] = None,  # connector_instance_id -> external id
        detected_by_sync_run: Optional[str] = None,
    ) -> List[ExternalConflict]:
        """Detect conflicts between external sources for a specific entity.

        Every pair of sources with differing values produces a persisted, open
        ExternalConflict. No silent winner is chosen at detection time.
        """
        external_ids = external_ids or {}
        conflicts: List[ExternalConflict] = []
        source_items = list(source_values.items())
        
        authorities = await self.get_authority_for_domain(db, organization_id, entity_type)
        authority_by_instance = {a.connector_instance_id: a for a in authorities}
        
        for i in range(len(source_items)):
            for j in range(i + 1, len(source_items)):
                source_a_id, value_a = source_items[i]
                source_b_id, value_b = source_items[j]
                
                if value_a != value_b:
                    auth_a = authority_by_instance.get(source_a_id)
                    auth_b = authority_by_instance.get(source_b_id)
                    
                    conflict_fields = []
                    if isinstance(value_a, dict) and isinstance(value_b, dict):
                        conflict_fields = sorted(set(value_a.keys()) & set(value_b.keys()))
                    
                    conflict = ExternalConflict(
                        organization_id=organization_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        source_a_instance_id=source_a_id,
                        source_a_external_id=external_ids.get(source_a_id, entity_id),
                        source_a_value=value_a,
                        source_a_timestamp=utcnow(),
                        source_a_authority=auth_a.precedence if auth_a else 0,
                        source_b_instance_id=source_b_id,
                        source_b_external_id=external_ids.get(source_b_id, entity_id),
                        source_b_value=value_b,
                        source_b_timestamp=utcnow(),
                        source_b_authority=auth_b.precedence if auth_b else 0,
                        conflict_fields=conflict_fields,
                        detected_at=utcnow(),
                        detected_by_sync_run=detected_by_sync_run,
                        resolution_state="open",
                    )
                    db.add(conflict)
                    conflicts.append(conflict)
        
        if conflicts:
            await db.flush()
            for conflict in conflicts:
                await publish_event(
                    db,
                    name="external_conflict.detected",
                    organization_id=organization_id,
                    payload={
                        "conflict_id": conflict.id,
                        "entity_type": entity_type,
                        "entity_id": entity_id,
                    },
                )
        
        return conflicts

    # ------------------------------------------------------------ Authority Queries
    
    async def list_authorities(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        entity_type: Optional[str] = None,
        authority_level: Optional[str] = None,
    ) -> List[SourceAuthority]:
        """List source authorities with filters."""
        query = select(SourceAuthority).where(
            SourceAuthority.organization_id == organization_id
        )
        
        if entity_type:
            query = query.where(SourceAuthority.entity_type == entity_type)
        if authority_level:
            query = query.where(SourceAuthority.authority_level == authority_level)
        
        query = query.order_by(SourceAuthority.entity_type, desc(SourceAuthority.precedence))
        result = await db.execute(query)
        return list(result.scalars().all())

    async def remove_authority(
        self,
        db: AsyncSession,
        authority_id: str,
        organization_id: str,
    ) -> bool:
        """Remove a source authority configuration."""
        authority = await db.get(SourceAuthority, authority_id)
        if not authority or authority.organization_id != organization_id:
            return False
        
        await db.delete(authority)
        await db.flush()
        return True


# Global instance
source_authority_service = SourceAuthorityService()