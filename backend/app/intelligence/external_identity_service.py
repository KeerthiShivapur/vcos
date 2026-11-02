"""Gate 24 — External Identity Mapping Service.

Implements canonical external identity mapping:
VCOS Person/Account ↔ External Provider Identity

The same employee may exist as:
VCOS Person
   │
   ├── Google ID
   ├── Microsoft ID
   ├── Slack ID
   ├── GitHub ID
   ├── Jira ID
   ├── Salesforce ID
   └── HR-system ID

These must NOT become seven different people.
But don't blindly merge based on email either.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    ExternalIdentityMapping,
    ExternalIdentityMappingHistory,
    ConnectorInstance,
    MAPPING_STATES,
    compute_payload_fingerprint,
)

logger = logging.getLogger("vcos.integration.identity")


class ExternalIdentityMappingService:
    """Service for managing external identity mappings."""
    
    # ------------------------------------------------------------ Mapping Creation
    
    async def create_mapping(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        vcos_entity_type: str,
        vcos_entity_id: str,
        external_id: str,
        external_email: Optional[str] = None,
        external_display_name: Optional[str] = None,
        external_avatar_url: Optional[str] = None,
        external_metadata: Optional[dict[str, Any]] = None,
        mapping_state: str = "pending",
        confidence: Optional[float] = None,
        resolution_method: str = "auto",
        resolved_by: Optional[str] = None,
        resolution_notes: Optional[str] = None,
        valid_from: Optional[datetime] = None,
        valid_until: Optional[datetime] = None,
        source_event_id: Optional[str] = None,
        sync_run_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> ExternalIdentityMapping:
        """Create a new external identity mapping."""
        
        # Validate connector instance
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if instance is None or instance.organization_id != organization_id:
            raise ValueError("Invalid connector instance")
        
        if mapping_state not in MAPPING_STATES:
            raise ValueError(f"Invalid mapping state: {mapping_state}")
        
        # Check for existing mapping to same VCOS entity
        existing_vcos = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.connector_instance_id == connector_instance_id,
                ExternalIdentityMapping.vcos_entity_type == vcos_entity_type,
                ExternalIdentityMapping.vcos_entity_id == vcos_entity_id,
            )
        )
        if existing_vcos.scalar_one_or_none():
            raise ValueError(
                f"VCOS entity {vcos_entity_type}:{vcos_entity_id} already mapped to this connector"
            )
        
        # Check for existing mapping to same external ID
        existing_ext = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.connector_instance_id == connector_instance_id,
                ExternalIdentityMapping.external_id == external_id,
            )
        )
        existing_mapping = existing_ext.scalar_one_or_none()
        if existing_mapping:
            # This is a conflict - same external ID mapped to different VCOS entity
            if existing_mapping.vcos_entity_id != vcos_entity_id:
                # Need to update the existing mapping to conflict state first
                existing_mapping.mapping_state = "conflict"
                existing_mapping.conflict_with = f"new:{vcos_entity_type}:{vcos_entity_id}"
                existing_mapping.conflict_details = {
                    "type": "external_id_collision",
                    "existing_vcos_entity": f"{existing_mapping.vcos_entity_type}:{existing_mapping.vcos_entity_id}",
                    "new_vcos_entity": f"{vcos_entity_type}:{vcos_entity_id}",
                    "detected_at": utcnow().isoformat(),
                }
                await db.flush()
                
                return await self._handle_mapping_conflict(
                    db=db,
                    existing_mapping=existing_mapping,
                    new_vcos_entity_type=vcos_entity_type,
                    new_vcos_entity_id=vcos_entity_id,
                    external_email=external_email,
                    external_display_name=external_display_name,
                    external_metadata=external_metadata,
                    source_event_id=source_event_id,
                    sync_run_id=sync_run_id,
                )
            # Same mapping already exists, update it
            return await self.update_mapping(
                db=db,
                mapping_id=existing_mapping.id,
                external_email=external_email,
                external_display_name=external_display_name,
                external_avatar_url=external_avatar_url,
                external_metadata=external_metadata,
                confidence=confidence,
                mapping_state="mapped",
            )
        
        mapping = ExternalIdentityMapping(
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            vcos_entity_type=vcos_entity_type,
            vcos_entity_id=vcos_entity_id,
            external_id=external_id,
            external_email=external_email,
            external_display_name=external_display_name,
            external_avatar_url=external_avatar_url,
            external_metadata=external_metadata or {},
            mapping_state=mapping_state,
            confidence=confidence,
            resolution_method=resolution_method,
            resolved_by=resolved_by,
            resolved_at=utcnow() if resolution_method != "auto" else None,
            resolution_notes=resolution_notes,
            valid_from=valid_from,
            valid_until=valid_until,
            source_event_id=source_event_id,
            sync_run_id=sync_run_id,
            created_by=created_by,
        )
        
        db.add(mapping)
        await db.flush()
        
        await publish_event(
            db,
            name="identity_mapping.created",
            organization_id=organization_id,
            actor_id=created_by,
            payload={
                "mapping_id": mapping.id,
                "vcos_entity_type": vcos_entity_type,
                "vcos_entity_id": vcos_entity_id,
                "external_id": external_id,
                "mapping_state": mapping_state,
            },
        )
        
        return mapping
    
    async def _handle_mapping_conflict(
        self,
        db: AsyncSession,
        existing_mapping: ExternalIdentityMapping,
        new_vcos_entity_type: str,
        new_vcos_entity_id: str,
        external_email: Optional[str],
        external_display_name: Optional[str],
        external_metadata: Optional[dict],
        source_event_id: Optional[str],
        sync_run_id: Optional[str],
    ) -> ExternalIdentityMapping:
        """Handle a mapping conflict - same external ID, different VCOS entities.
        
        We don't create a second mapping (would violate unique constraint).
        Instead, we update the existing mapping to track the conflict.
        """
        
        # Update existing mapping to track conflict
        existing_mapping.mapping_state = "conflict"
        existing_mapping.conflict_details = {
            "type": "external_id_collision",
            "primary_vcos_entity": f"{existing_mapping.vcos_entity_type}:{existing_mapping.vcos_entity_id}",
            "alternative_vcos_entity": f"{new_vcos_entity_type}:{new_vcos_entity_id}",
            "detected_at": utcnow().isoformat(),
        }
        
        await db.flush()
        
        await publish_event(
            db,
            name="identity_mapping.conflict_detected",
            organization_id=existing_mapping.organization_id,
            payload={
                "mapping_id": existing_mapping.id,
                "external_id": existing_mapping.external_id,
                "primary_vcos": f"{existing_mapping.vcos_entity_type}:{existing_mapping.vcos_entity_id}",
                "alternative_vcos": f"{new_vcos_entity_type}:{new_vcos_entity_id}",
            },
        )
        
        return existing_mapping
    
    # ------------------------------------------------------------ Mapping Queries
    
    async def get_mapping(
        self, db: AsyncSession, organization_id: str, mapping_id: str
    ) -> Optional[ExternalIdentityMapping]:
        """Get a mapping by ID."""
        mapping = await db.get(ExternalIdentityMapping, mapping_id)
        if mapping is None or mapping.organization_id != organization_id:
            return None
        return mapping
    
    async def get_mapping_by_vcos(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: str,
        vcos_entity_type: str,
        vcos_entity_id: str,
    ) -> Optional[ExternalIdentityMapping]:
        """Get mapping for a VCOS entity."""
        result = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.connector_instance_id == connector_instance_id,
                ExternalIdentityMapping.vcos_entity_type == vcos_entity_type,
                ExternalIdentityMapping.vcos_entity_id == vcos_entity_id,
            )
        )
        return result.scalar_one_or_none()
    
    async def get_mapping_by_external(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: str,
        external_id: str,
    ) -> Optional[ExternalIdentityMapping]:
        """Get mapping for an external ID."""
        result = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.connector_instance_id == connector_instance_id,
                ExternalIdentityMapping.external_id == external_id,
            )
        )
        return result.scalar_one_or_none()
    
    async def list_mappings(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        connector_instance_id: Optional[str] = None,
        vcos_entity_type: Optional[str] = None,
        mapping_state: Optional[str] = None,
    ) -> list[ExternalIdentityMapping]:
        """List identity mappings with filters."""
        query = select(ExternalIdentityMapping).where(
            ExternalIdentityMapping.organization_id == organization_id
        )
        if connector_instance_id:
            query = query.where(ExternalIdentityMapping.connector_instance_id == connector_instance_id)
        if vcos_entity_type:
            query = query.where(ExternalIdentityMapping.vcos_entity_type == vcos_entity_type)
        if mapping_state:
            query = query.where(ExternalIdentityMapping.mapping_state == mapping_state)
        query = query.order_by(ExternalIdentityMapping.created_at.desc())
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_conflicts(
        self, db: AsyncSession, organization_id: str
    ) -> list[ExternalIdentityMapping]:
        """Get all mappings in conflict state."""
        result = await db.execute(
            select(ExternalIdentityMapping).where(
                ExternalIdentityMapping.organization_id == organization_id,
                ExternalIdentityMapping.mapping_state == "conflict",
            )
        )
        return list(result.scalars().all())
    
    # ------------------------------------------------------------ Mapping Updates
    
    async def update_mapping(
        self,
        db: AsyncSession,
        mapping_id: str,
        **fields: Any,
    ) -> Optional[ExternalIdentityMapping]:
        """Update a mapping."""
        mapping = await db.get(ExternalIdentityMapping, mapping_id)
        if mapping is None:
            return None
        
        old_state = mapping.mapping_state
        
        for key, value in fields.items():
            if value is not None and hasattr(mapping, key):
                # Record history for important fields
                if key in ("mapping_state", "confidence", "external_email", "external_display_name"):
                    old_value = getattr(mapping, key, None)
                    if old_value != value:
                        await self._record_history(
                            db, mapping, key, str(old_value) if old_value else None,
                            str(value) if value else None, "update"
                        )
                setattr(mapping, key, value)
        
        if "mapping_state" in fields and fields["mapping_state"] == "mapped":
            mapping.resolved_at = utcnow()
        
        mapping.updated_at = utcnow()
        await db.flush()
        
        if old_state != mapping.mapping_state:
            await publish_event(
                db,
                name="identity_mapping.state_changed",
                organization_id=mapping.organization_id,
                payload={
                    "mapping_id": mapping_id,
                    "old_state": old_state,
                    "new_state": mapping.mapping_state,
                },
            )
        
        return mapping
    
    async def resolve_conflict(
        self,
        db: AsyncSession,
        mapping_id: str,
        chosen_vcos_entity_id: str,
        resolution_method: str = "manual",
        resolved_by: Optional[str] = None,
        resolution_notes: Optional[str] = None,
    ) -> Optional[ExternalIdentityMapping]:
        """Resolve a mapping conflict by choosing the correct VCOS entity."""
        
        mapping = await db.get(ExternalIdentityMapping, mapping_id)
        if mapping is None or mapping.mapping_state != "conflict":
            return None
        
        # Update the chosen mapping to mapped state
        mapping.mapping_state = "mapped"
        mapping.vcos_entity_id = chosen_vcos_entity_id
        mapping.resolution_method = resolution_method
        mapping.resolved_by = resolved_by
        mapping.resolved_at = utcnow()
        mapping.resolution_notes = resolution_notes
        mapping.conflict_with = None
        mapping.conflict_details = None
        
        # Mark conflicting mapping as ignored
        if mapping.conflict_with:
            conflict_id = mapping.conflict_with.replace("new:", "")
            conflict_mapping = await db.get(ExternalIdentityMapping, conflict_id)
            if conflict_mapping:
                conflict_mapping.mapping_state = "ignored"
                conflict_mapping.conflict_with = None
                conflict_mapping.conflict_details = None
                await db.flush()
        
        mapping.updated_at = utcnow()
        await db.flush()
        
        await publish_event(
            db,
            name="identity_mapping.conflict_resolved",
            organization_id=mapping.organization_id,
            actor_id=resolved_by,
            payload={
                "mapping_id": mapping_id,
                "chosen_vcos_entity_id": chosen_vcos_entity_id,
                "resolution_method": resolution_method,
            },
        )
        
        return mapping
    
    async def ignore_mapping(
        self,
        db: AsyncSession,
        mapping_id: str,
        ignored_by: Optional[str] = None,
    ) -> Optional[ExternalIdentityMapping]:
        """Mark a mapping as ignored (e.g., external entity doesn't correspond to VCOS entity)."""
        
        mapping = await db.get(ExternalIdentityMapping, mapping_id)
        if mapping is None:
            return None
        
        mapping.mapping_state = "ignored"
        mapping.resolution_method = "manual"
        mapping.resolved_by = ignored_by
        mapping.resolved_at = utcnow()
        mapping.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="identity_mapping.ignored",
            organization_id=mapping.organization_id,
            actor_id=ignored_by,
            payload={"mapping_id": mapping_id},
        )
        
        return mapping
    
    async def delete_mapping(
        self,
        db: AsyncSession,
        mapping_id: str,
        actor_id: Optional[str] = None,
    ) -> bool:
        """Delete a mapping."""
        
        mapping = await db.get(ExternalIdentityMapping, mapping_id)
        if mapping is None:
            return False
        
        await db.delete(mapping)
        await db.flush()
        
        await publish_event(
            db,
            name="identity_mapping.deleted",
            organization_id=mapping.organization_id,
            actor_id=actor_id,
            payload={"mapping_id": mapping_id},
        )
        
        return True
    
    # ------------------------------------------------------------ Bulk Operations
    
    async def bulk_create_mappings(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        mappings: list[dict[str, Any]],
        source_event_id: Optional[str] = None,
        sync_run_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """Bulk create mappings from external sync."""
        
        created = 0
        updated = 0
        conflicts = 0
        errors = []
        
        for i, mapping_data in enumerate(mappings):
            try:
                vcos_entity_type = mapping_data.get("vcos_entity_type")
                vcos_entity_id = mapping_data.get("vcos_entity_id")
                external_id = mapping_data.get("external_id")
                
                if not all([vcos_entity_type, vcos_entity_id, external_id]):
                    errors.append(f"Mapping {i}: missing required fields")
                    continue
                
                existing = await self.get_mapping_by_external(
                    db, organization_id, connector_instance_id, external_id
                )
                
                if existing:
                    if existing.vcos_entity_id != vcos_entity_id:
                        await self._handle_mapping_conflict(
                            db=db,
                            existing_mapping=existing,
                            new_vcos_entity_type=vcos_entity_type,
                            new_vcos_entity_id=vcos_entity_id,
                            external_email=mapping_data.get("external_email"),
                            external_display_name=mapping_data.get("external_display_name"),
                            external_metadata=mapping_data.get("external_metadata"),
                            source_event_id=source_event_id,
                            sync_run_id=sync_run_id,
                        )
                        conflicts += 1
                    else:
                        await self.update_mapping(
                            db=db,
                            mapping_id=existing.id,
                            external_email=mapping_data.get("external_email"),
                            external_display_name=mapping_data.get("external_display_name"),
                            external_metadata=mapping_data.get("external_metadata"),
                            mapping_state="mapped",
                        )
                        updated += 1
                else:
                    await self.create_mapping(
                        db=db,
                        organization_id=organization_id,
                        connector_instance_id=connector_instance_id,
                        vcos_entity_type=vcos_entity_type,
                        vcos_entity_id=vcos_entity_id,
                        external_id=external_id,
                        external_email=mapping_data.get("external_email"),
                        external_display_name=mapping_data.get("external_display_name"),
                        external_metadata=mapping_data.get("external_metadata"),
                        mapping_state="mapped",
                        source_event_id=source_event_id,
                        sync_run_id=sync_run_id,
                    )
                    created += 1
                    
            except Exception as e:
                errors.append(f"Mapping {i}: {str(e)}")
        
        return {
            "created": created,
            "updated": updated,
            "conflicts": conflicts,
            "errors": errors,
        }
    
    # ------------------------------------------------------------ History & Audit
    
    async def _record_history(
        self,
        db: AsyncSession,
        mapping: ExternalIdentityMapping,
        field_changed: str,
        old_value: Optional[str],
        new_value: Optional[str],
        change_reason: str,
        changed_by: Optional[str] = None,
        sync_run_id: Optional[str] = None,
        source_event_id: Optional[str] = None,
    ) -> ExternalIdentityMappingHistory:
        """Record a mapping change in history."""
        
        history = ExternalIdentityMappingHistory(
            organization_id=mapping.organization_id,
            mapping_id=mapping.id,
            field_changed=field_changed,
            old_value=old_value,
            new_value=new_value,
            change_reason=change_reason,
            changed_by=changed_by,
            sync_run_id=sync_run_id,
            source_event_id=source_event_id,
        )
        
        db.add(history)
        await db.flush()
        return history
    
    async def get_mapping_history(
        self,
        db: AsyncSession,
        organization_id: str,
        mapping_id: str,
    ) -> list[ExternalIdentityMappingHistory]:
        """Get history for a mapping."""
        result = await db.execute(
            select(ExternalIdentityMappingHistory).where(
                ExternalIdentityMappingHistory.organization_id == organization_id,
                ExternalIdentityMappingHistory.mapping_id == mapping_id,
            ).order_by(ExternalIdentityMappingHistory.changed_at.desc())
        )
        return list(result.scalars().all())


external_identity_mapping_service = ExternalIdentityMappingService()