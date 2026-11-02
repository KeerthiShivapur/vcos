"""Gate 24 — Source Authority & Conflict Preservation Service.

Implements governed source-authority semantics and conflict preservation.

Different systems may be authoritative for different domains.
Do NOT hard-code a universal winner. Build governed source-authority semantics.

If external systems disagree, do NOT silently overwrite.
Preserve: Source A, Source B, Timestamps, Provenance, Conflict, Authority, Resolution
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    SourceAuthority,
    ExternalConflict,
    ConnectorInstance,
    SOURCE_AUTHORITY_LEVELS,
    CONFLICT_RESOLUTION_STATES,
)
from app.intelligence.external_identity_service import external_identity_mapping_service

logger = logging.getLogger("vcos.integration.conflict")


class SourceAuthorityService:
    """Service for managing source authority and conflict preservation."""
    
    # ------------------------------------------------------------ Source Authority
    
    async def set_source_authority(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        connector_instance_id: str,
        authority_level: str = "secondary",
        precedence: int = 0,
        field_scope: Optional[list[str]] = None,
        conditions: Optional[dict] = None,
        configured_by: Optional[str] = None,
        approved_by: Optional[str] = None,
    ) -> SourceAuthority:
        """Set or update source authority for an entity type."""
        
        if authority_level not in SOURCE_AUTHORITY_LEVELS:
            raise ValueError(f"Invalid authority level: {authority_level}")
        
        # Validate connector instance
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if instance is None or instance.organization_id != organization_id:
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
            authority.authority_level = authority_level
            authority.precedence = precedence
            authority.field_scope = field_scope or []
            authority.conditions = conditions
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
        return authority
    
    async def get_authorities(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: Optional[str] = None,
    ) -> list[SourceAuthority]:
        """Get source authorities for an organization."""
        query = select(SourceAuthority).where(
            SourceAuthority.organization_id == organization_id
        )
        if entity_type:
            query = query.where(SourceAuthority.entity_type == entity_type)
        query = query.order_by(desc(SourceAuthority.precedence), SourceAuthority.entity_type)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_primary_authority(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
    ) -> Optional[SourceAuthority]:
        """Get the primary authority for an entity type."""
        result = await db.execute(
            select(SourceAuthority).where(
                SourceAuthority.organization_id == organization_id,
                SourceAuthority.entity_type == entity_type,
                SourceAuthority.authority_level == "primary",
            ).order_by(desc(SourceAuthority.precedence))
        )
        return result.scalar_one_or_none()
    
    async def delete_authority(
        self, db: AsyncSession, authority_id: str
    ) -> bool:
        """Delete a source authority."""
        authority = await db.get(SourceAuthority, authority_id)
        if authority is None:
            return False
        await db.delete(authority)
        await db.flush()
        return True
    
    # ------------------------------------------------------------ Conflict Detection
    
    async def detect_conflict(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entity_type: str,
        entity_id: Optional[str],
        source_a_instance_id: str,
        source_a_external_id: str,
        source_a_value: dict[str, Any],
        source_a_timestamp: datetime,
        source_b_instance_id: str,
        source_b_external_id: str,
        source_b_value: dict[str, Any],
        source_b_timestamp: datetime,
        source_a_authority: int = 0,
        source_b_authority: int = 0,
        conflict_fields: Optional[list[str]] = None,
        detected_by_sync_run: Optional[str] = None,
        source_a_event_id: Optional[str] = None,
        source_b_event_id: Optional[str] = None,
    ) -> ExternalConflict:
        """Detect and record a conflict between two sources."""
        
        # Validate both connector instances
        for inst_id in [source_a_instance_id, source_b_instance_id]:
            instance = await db.get(ConnectorInstance, inst_id)
            if instance is None or instance.organization_id != organization_id:
                raise ValueError(f"Invalid connector instance: {inst_id}")
        
        # Check for existing unresolved conflict
        existing = await db.execute(
            select(ExternalConflict).where(
                ExternalConflict.organization_id == organization_id,
                ExternalConflict.entity_type == entity_type,
                ExternalConflict.entity_id == entity_id,
                ExternalConflict.resolution_state == "open",
            )
        )
        existing_conflict = existing.scalar_one_or_none()
        
        if existing_conflict:
            # Update existing conflict with new source data
            existing_conflict.additional_sources = existing_conflict.additional_sources or []
            existing_conflict.additional_sources.append({
                "source_instance_id": source_b_instance_id,
                "external_id": source_b_external_id,
                "value": source_b_value,
                "timestamp": source_b_timestamp.isoformat(),
                "authority": source_b_authority,
                "event_id": source_b_event_id,
            })
            existing_conflict.conflict_fields = list(set(
                (existing_conflict.conflict_fields or []) + (conflict_fields or [])
            ))
            existing_conflict.updated_at = utcnow()
            
            await db.flush()
            return existing_conflict
        
        # Create new conflict
        conflict = ExternalConflict(
            organization_id=organization_id,
            entity_type=entity_type,
            entity_id=entity_id,
            source_a_instance_id=source_a_instance_id,
            source_a_external_id=source_a_external_id,
            source_a_value=source_a_value,
            source_a_timestamp=source_a_timestamp,
            source_a_authority=source_a_authority,
            source_b_instance_id=source_b_instance_id,
            source_b_external_id=source_b_external_id,
            source_b_value=source_b_value,
            source_b_timestamp=source_b_timestamp,
            source_b_authority=source_b_authority,
            conflict_fields=conflict_fields or [],
            detected_at=utcnow(),
            detected_by_sync_run=detected_by_sync_run,
            source_a_event_id=source_a_event_id,
            source_b_event_id=source_b_event_id,
        )
        
        db.add(conflict)
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.detected",
            organization_id=organization_id,
            payload={
                "conflict_id": conflict.id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "source_a": source_a_instance_id,
                "source_b": source_b_instance_id,
                "fields": conflict_fields,
            },
        )
        
        return conflict
    
    # ------------------------------------------------------------ Conflict Resolution
    
    async def resolve_conflict_by_authority(
        self,
        db: AsyncSession,
        conflict_id: str,
        resolved_by: Optional[str] = None,
        resolution_notes: Optional[str] = None,
    ) -> Optional[ExternalConflict]:
        """Resolve a conflict using source authority precedence."""
        
        conflict = await db.get(ExternalConflict, conflict_id)
        if conflict is None or conflict.resolution_state != "open":
            return None
        
        # Determine winner by authority
        if conflict.source_a_authority >= conflict.source_b_authority:
            winner = "source_a"
            resolved_value = conflict.source_a_value
        else:
            winner = "source_b"
            resolved_value = conflict.source_b_value
        
        conflict.resolution_state = "authority_applied"
        conflict.resolution_method = "authority"
        conflict.resolved_value = resolved_value
        conflict.resolved_by = resolved_by
        conflict.resolved_at = utcnow()
        conflict.resolution_notes = resolution_notes or f"Resolved by authority: {winner}"
        conflict.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.resolved",
            organization_id=conflict.organization_id,
            actor_id=resolved_by,
            payload={
                "conflict_id": conflict_id,
                "method": "authority",
                "winner": winner,
            },
        )
        
        return conflict
    
    async def resolve_conflict_manually(
        self,
        db: AsyncSession,
        conflict_id: str,
        resolved_value: dict[str, Any],
        resolved_by: str,
        resolution_notes: Optional[str] = None,
    ) -> Optional[ExternalConflict]:
        """Manually resolve a conflict with a specific value."""
        
        conflict = await db.get(ExternalConflict, conflict_id)
        if conflict is None or conflict.resolution_state != "open":
            return None
        
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
            name="external_conflict.resolved",
            organization_id=conflict.organization_id,
            actor_id=resolved_by,
            payload={
                "conflict_id": conflict_id,
                "method": "manual",
            },
        )
        
        return conflict
    
    async def merge_conflict(
        self,
        db: AsyncSession,
        conflict_id: str,
        merged_value: dict[str, Any],
        resolved_by: str,
        resolution_notes: Optional[str] = None,
    ) -> Optional[ExternalConflict]:
        """Merge conflict values into a single canonical value."""
        
        conflict = await db.get(ExternalConflict, conflict_id)
        if conflict is None or conflict.resolution_state != "open":
            return None
        
        conflict.resolution_state = "merged"
        conflict.resolution_method = "merged"
        conflict.resolved_value = merged_value
        conflict.resolved_by = resolved_by
        conflict.resolved_at = utcnow()
        conflict.resolution_notes = resolution_notes
        conflict.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_conflict.resolved",
            organization_id=conflict.organization_id,
            actor_id=resolved_by,
            payload={
                "conflict_id": conflict_id,
                "method": "merged",
            },
        )
        
        return conflict
    
    # ------------------------------------------------------------ Conflict Queries
    
    async def get_conflict(
        self, db: AsyncSession, conflict_id: str
    ) -> Optional[ExternalConflict]:
        """Get a conflict by ID."""
        return await db.get(ExternalConflict, conflict_id)
    
    async def list_conflicts(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        entity_type: Optional[str] = None,
        resolution_state: Optional[str] = None,
        limit: int = 100,
    ) -> list[ExternalConflict]:
        """List conflicts with filters."""
        query = select(ExternalConflict).where(
            ExternalConflict.organization_id == organization_id
        )
        if entity_type:
            query = query.where(ExternalConflict.entity_type == entity_type)
        if resolution_state:
            query = query.where(ExternalConflict.resolution_state == resolution_state)
        query = query.order_by(desc(ExternalConflict.detected_at)).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_open_conflicts(
        self, db: AsyncSession, organization_id: str
    ) -> list[ExternalConflict]:
        """Get all open conflicts."""
        return await self.list_conflicts(
            db, organization_id, resolution_state="open"
        )
    
    # ------------------------------------------------------------ Authority-based Canonical Resolution
    
    async def get_canonical_value(
        self,
        db: AsyncSession,
        organization_id: str,
        entity_type: str,
        entity_id: str,
    ) -> tuple[Optional[dict], Optional[str]]:
        """
        Get the canonical value for an entity based on source authority.
        
        Returns: (canonical_value, winning_source_instance_id)
        """
        
        # Get all authorities for this entity type
        authorities = await self.get_authorities(db, organization_id, entity_type)
        
        if not authorities:
            return None, None
        
        # Get the highest precedence authority that has data for this entity
        # This would require checking the actual connector data
        # For now, return the primary authority
        primary = next((a for a in authorities if a.authority_level == "primary"), None)
        
        if primary:
            # The actual value would be fetched from the connector
            return None, primary.connector_instance_id
        
        # Fall back to highest precedence
        highest = max(authorities, key=lambda a: a.precedence)
        return None, highest.connector_instance_id


source_authority_service = SourceAuthorityService()