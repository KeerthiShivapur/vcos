"""External Identity Service — universal external identity resolution.

Implements:
- External identity resolution across providers
- Identity mapping with conflict detection
- Governed identity resolution (no silent merges)
- Historical mapping preservation
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Optional, List, Dict

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    ExternalIdentityMapping,
    ExternalIdentityMappingHistory,
    ConnectorInstance,
    MAPPING_STATES,
)
from app.models.people_intelligence import PersonIdentity, IDENTITY_SOURCES

logger = logging.getLogger("vcos.integration.identity")


class ExternalIdentityService:
    """Universal external identity resolution service.
    
    Resolves external identities (Google, Microsoft, Slack, GitHub, etc.)
    to canonical VCOS persons. Never silently merges ambiguous identities.
    """

    # ------------------------------------------------------------ Identity Resolution
    
    async def resolve_identity(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        external_id: str,
        external_email: Optional[str] = None,
        external_display_name: Optional[str] = None,
        external_avatar_url: Optional[str] = None,
        external_metadata: Optional[Dict] = None,
        source_event_id: Optional[str] = None,
        sync_run_id: Optional[str] = None,
    ) -> ExternalIdentityMapping:
        """Resolve an external identity to a VCOS person.
        
        Returns the existing mapping if found, creates a new pending mapping if not.
        Never silently merges — ambiguous cases become 'conflict' state.
        """
        # Validate connector instance belongs to organization
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if not instance or instance.organization_id != organization_id:
            raise ValueError("Connector instance does not belong to organization")
        
        # Check for existing mapping by external_id
        existing = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.connector_instance_id == connector_instance_id,
                ExternalIdentityMapping.external_id == external_id,
            )
        )
        mapping = existing.scalar_one_or_none()
        
        if mapping:
            # Update metadata if provided
            if external_email and mapping.external_email != external_email:
                mapping.external_email = external_email
            if external_display_name and mapping.external_display_name != external_display_name:
                mapping.external_display_name = external_display_name
            if external_avatar_url and mapping.external_avatar_url != external_avatar_url:
                mapping.external_avatar_url = external_avatar_url
            if external_metadata:
                mapping.external_metadata = {**mapping.external_metadata, **external_metadata}
            
            mapping.updated_at = utcnow()
            await db.flush()
            return mapping
        
        # Check for email-based conflicts (same email, different external_id)
        if external_email:
            email_mappings = await db.execute(
                select(ExternalIdentityMapping).where(
                    ExternalIdentityMapping.organization_id == organization_id,
                    ExternalIdentityMapping.external_email == external_email,
                    ExternalIdentityMapping.external_id != external_id,
                    ExternalIdentityMapping.mapping_state.in_(["mapped", "pending"]),
                )
            )
            conflicts = list(email_mappings.scalars().all())
            
            if conflicts:
                # Create conflict mapping
                return await self._create_conflict_mapping(
                    db=db,
                    organization_id=organization_id,
                    connector_instance_id=connector_instance_id,
                    external_id=external_id,
                    external_email=external_email,
                    external_display_name=external_display_name,
                    external_avatar_url=external_avatar_url,
                    external_metadata=external_metadata,
                    conflicts=conflicts,
                    source_event_id=source_event_id,
                    sync_run_id=sync_run_id,
                )
        
        # No existing mapping — create pending
        mapping = ExternalIdentityMapping(
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            vcos_entity_type="person",
            vcos_entity_id="",  # Will be resolved later
            external_id=external_id,
            external_email=external_email,
            external_display_name=external_display_name,
            external_avatar_url=external_avatar_url,
            external_metadata=external_metadata or {},
            mapping_state="pending",
            confidence=None,
            resolution_method="auto",
            source_event_id=source_event_id,
            sync_run_id=sync_run_id,
        )
        db.add(mapping)
        await db.flush()
        
        await publish_event(
            db,
            name="external_identity.mapping_created",
            organization_id=organization_id,
            payload={
                "mapping_id": mapping.id,
                "connector_instance_id": connector_instance_id,
                "external_id": external_id,
                "external_email": external_email,
            },
        )
        
        return mapping

    async def _create_conflict_mapping(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        external_id: str,
        external_email: Optional[str],
        external_display_name: Optional[str],
        external_avatar_url: Optional[str],
        external_metadata: Optional[Dict],
        conflicts: List,
        source_event_id: Optional[str],
        sync_run_id: Optional[str],
    ) -> ExternalIdentityMapping:
        """Create a mapping in conflict state with existing mappings."""
        primary_conflict = conflicts[0]
        
        mapping = ExternalIdentityMapping(
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            vcos_entity_type="person",
            vcos_entity_id=primary_conflict.vcos_entity_id,
            external_id=external_id,
            external_email=external_email,
            external_display_name=external_display_name,
            external_avatar_url=external_avatar_url,
            external_metadata=external_metadata or {},
            mapping_state="conflict",
            confidence=None,
            resolution_method="auto",
            conflict_with=primary_conflict.id,
            conflict_details={
                "type": "email_collision",
                "conflicting_external_ids": [c.external_id for c in conflicts],
                "conflicting_mapping_ids": [c.id for c in conflicts],
            },
            source_event_id=source_event_id,
            sync_run_id=sync_run_id,
        )
        db.add(mapping)
        
        # Update conflicting mappings
        for c in conflicts:
            c.conflict_with = mapping.id
            c.conflict_details = {
                "type": "email_collision",
                "conflicting_external_id": external_id,
                "conflicting_mapping_id": mapping.id,
            }
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_identity.conflict_detected",
            organization_id=organization_id,
            payload={
                "mapping_id": mapping.id,
                "conflicting_mapping_ids": [c.id for c in conflicts],
                "external_email": external_email,
            },
        )
        
        return mapping

    # ------------------------------------------------------------ Governed Resolution
    
    async def resolve_mapping(
        self,
        db: AsyncSession,
        *,
        mapping_id: str,
        organization_id: str,
        resolved_by: str,
        vcos_entity_id: str,
        resolution_method: str = "manual",
        resolution_notes: Optional[str] = None,
    ) -> ExternalIdentityMapping:
        """Governed identity resolution — explicitly link external identity to VCOS person."""
        mapping = await db.get(ExternalIdentityMapping, mapping_id)
        if not mapping or mapping.organization_id != organization_id:
            raise ValueError("Mapping not found")
        
        if mapping.mapping_state not in ("pending", "conflict"):
            raise ValueError(f"Cannot resolve mapping in state: {mapping.mapping_state}")
        
        # Record history
        history = ExternalIdentityMappingHistory(
            organization_id=organization_id,
            mapping_id=mapping_id,
            field_changed="vcos_entity_id",
            old_value=mapping.vcos_entity_id or "",
            new_value=vcos_entity_id,
            change_reason=resolution_notes or f"Resolved via {resolution_method}",
            changed_by=resolved_by,
            source_event_id=None,
            sync_run_id=None,
        )
        db.add(history)
        
        # Record conflict resolution if applicable
        if mapping.conflict_with:
            history2 = ExternalIdentityMappingHistory(
                organization_id=organization_id,
                mapping_id=mapping_id,
                field_changed="mapping_state",
                old_value="conflict",
                new_value="mapped",
                change_reason=f"Resolved conflict with {mapping.conflict_with} via {resolution_method}",
                changed_by=resolved_by,
            )
            db.add(history2)
        
        # Update mapping
        mapping.vcos_entity_id = vcos_entity_id
        mapping.mapping_state = "mapped"
        mapping.confidence = 1.0
        mapping.resolution_method = resolution_method
        mapping.resolved_by = resolved_by
        mapping.resolved_at = utcnow()
        mapping.resolution_notes = resolution_notes
        mapping.conflict_with = None
        mapping.conflict_details = None
        mapping.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_identity.resolved",
            organization_id=organization_id,
            payload={
                "mapping_id": mapping.id,
                "vcos_entity_id": vcos_entity_id,
                "resolved_by": resolved_by,
                "method": resolution_method,
            },
        )
        
        return mapping

    async def ignore_mapping(
        self,
        db: AsyncSession,
        *,
        mapping_id: str,
        organization_id: str,
        ignored_by: str,
        notes: Optional[str] = None,
    ) -> ExternalIdentityMapping:
        """Mark an external identity as intentionally ignored (not a VCOS person)."""
        mapping = await db.get(ExternalIdentityMapping, mapping_id)
        if not mapping or mapping.organization_id != organization_id:
            raise ValueError("Mapping not found")
        
        history = ExternalIdentityMappingHistory(
            organization_id=organization_id,
            mapping_id=mapping_id,
            field_changed="mapping_state",
            old_value=mapping.mapping_state,
            new_value="ignored",
            change_reason=notes or "Intentionally ignored",
            changed_by=ignored_by,
        )
        db.add(history)
        
        mapping.mapping_state = "ignored"
        mapping.updated_at = utcnow()
        
        await db.flush()
        return mapping

    # ------------------------------------------------------------ Identity Discovery
    
    async def discover_identities(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        external_people: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Batch discover and resolve identities from external system.
        
        Args:
            external_people: List of dicts with keys:
                - external_id (required)
                - email (optional)
                - display_name (optional)
                - avatar_url (optional)
                - metadata (optional)
        
        Returns:
            Dict with counts: created, updated, conflicts, ignored
        """
        stats = {"created": 0, "updated": 0, "conflicts": 0, "ignored": 0}
        
        for person in external_people:
            external_id = person.get("external_id")
            if not external_id:
                continue
            
            mapping = await self.resolve_identity(
                db=db,
                organization_id=organization_id,
                connector_instance_id=connector_instance_id,
                external_id=external_id,
                external_email=person.get("email"),
                external_display_name=person.get("display_name"),
                external_avatar_url=person.get("avatar_url"),
                external_metadata=person.get("metadata"),
            )
            
            if mapping.mapping_state == "pending" and mapping.vcos_entity_id:
                stats["created"] += 1
            elif mapping.mapping_state == "mapped" and not mapping.conflict_with:
                stats["updated"] += 1
            elif mapping.mapping_state == "conflict":
                stats["conflicts"] += 1
            elif mapping.mapping_state == "ignored":
                stats["ignored"] += 1
        
        await db.flush()
        return stats

    # ------------------------------------------------------------ Identity Queries
    
    async def get_mappings(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        connector_instance_id: Optional[str] = None,
        vcos_entity_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[ExternalIdentityMapping]:
        """Query identity mappings."""
        query = select(ExternalIdentityMapping).where(
            ExternalIdentityMapping.organization_id == organization_id
        )
        
        if connector_instance_id:
            query = query.where(ExternalIdentityMapping.connector_instance_id == connector_instance_id)
        if vcos_entity_id:
            query = query.where(ExternalIdentityMapping.vcos_entity_id == vcos_entity_id)
        if state:
            query = query.where(ExternalIdentityMapping.mapping_state == state)
        
        query = query.order_by(ExternalIdentityMapping.created_at.desc()).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_conflicts(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        connector_instance_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ExternalIdentityMapping]:
        """Get all mappings in conflict state."""
        query = select(ExternalIdentityMapping).where(
            ExternalIdentityMapping.organization_id == organization_id,
            ExternalIdentityMapping.mapping_state == "conflict",
        )
        
        if connector_instance_id:
            query = query.where(ExternalIdentityMapping.connector_instance_id == connector_instance_id)
        
        query = query.order_by(ExternalIdentityMapping.created_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_person_external_identities(
        self,
        db: AsyncSession,
        organization_id: str,
        person_id: str,
    ) -> List[ExternalIdentityMapping]:
        """Get all external identities linked to a VCOS person."""
        result = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.vcos_entity_id == person_id,
                ExternalIdentityMapping.mapping_state == "mapped",
            )
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------ Historical Mappings
    
    async def get_mapping_history(
        self,
        db: AsyncSession,
        mapping_id: str,
    ) -> List[ExternalIdentityMappingHistory]:
        """Get history of changes to an identity mapping."""
        result = await db.execute(
            select(ExternalIdentityMappingHistory).where(
                ExternalIdentityMappingHistory.mapping_id == mapping_id
            ).order_by(ExternalIdentityMappingHistory.changed_at.desc())
        )
        return list(result.scalars().all())


# Global instance
external_identity_service = ExternalIdentityService()