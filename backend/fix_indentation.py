with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find and replace the _validate_current_state_uniqueness function
old_code = '''async def _validate_current_state_uniqueness(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    organization_id: str,
) -> bool:
    """Ensure only one current version exists where domain requires it."""
    # Entities that require single current version per organization
    current_state_entities = {
        "CompanyAuthorization": ["approved", "conditional"],
        "CompanyCommitment": ["authorized", "active", "pending_authorization"],
    }
    
    if entity_type not in current_state_entities:
        return True
    
    current_states = current_state_entities[entity_type]
    entity_state = getattr(entity, "state", None)
    
    if entity_state not in current_states:
        return True
    
    # Check if another current version exists
    model = type(entity)
    query = select(model).where(
        model.organization_id == organization_id,
        model.state.in_(current_states),
    )
    
    # Only exclude self if entity has an ID (for updates)
    entity_id = getattr(entity, "id", None)
    if entity_id:
        query = query.where(model.id != entity_id)
    
    existing = await db.execute(query)
    other_current = existing.scalars().first()
    
    if other_current:
        # Allow if the other is the superseded version
        # For CREATE mutations, entity.id may be None (not yet flushed), so don't allow the superseded check to pass
        entity_id = getattr(entity, "id", None)
        if entity_id is not None and getattr(other_current, "superseded_by_id", None) == entity_id:
            return True
        print(f"DEBUG _validate_current_state_uniqueness: about to raise TemporalViolation")
        raise TemporalViolation(
            f"Multiple current {entity_type} states not allowed. "
            f"Existing: {other_current.id} (state: {other_current.state}), "
            f"New: {entity.id if entity_id else 'new'} (state: {entity_state}). "
            f"Use supersession to transition."
        )

    return True'''

new_code = '''    async def _validate_current_state_uniqueness(
        self,
        db: AsyncSession,
        entity_type: str,
        entity: Any,
        organization_id: str,
    ) -> bool:
        """Ensure only one current version exists where domain requires it."""
        # Entities that require single current version per organization
        current_state_entities = {
            "CompanyAuthorization": ["approved", "conditional"],
            "CompanyCommitment": ["authorized", "active", "pending_authorization"],
        }
        
        if entity_type not in current_state_entities:
            return True
        
        current_states = current_state_entities[entity_type]
        entity_state = getattr(entity, "state", None)
        
        if entity_state not in current_states:
            return True
        
        # Check if another current version exists
        model = type(entity)
        query = select(model).where(
            model.organization_id == organization_id,
            model.state.in_(current_states),
        )
        
        # Only exclude self if entity has an ID (for updates)
        entity_id = getattr(entity, "id", None)
        if entity_id:
            query = query.where(model.id != entity_id)
        
        existing = await db.execute(query)
        other_current = existing.scalars().first()
        
        if other_current:
            # Allow if the other is the superseded version
            # For CREATE mutations, entity.id may be None (not yet flushed), so don't allow the superseded check to pass
            entity_id = getattr(entity, "id", None)
            if entity_id is not None and getattr(other_current, "superseded_by_id", None) == entity_id:
                return True
            print(f"DEBUG _validate_current_state_uniqueness: about to raise TemporalViolation")
            raise TemporalViolation(
                f"Multiple current {entity_type} states not allowed. "
                f"Existing: {other_current.id} (state: {other_current.state}), "
                f"New: {entity.id if entity_id else 'new'} (state: {entity_state}). "
                f"Use supersession to transition."
            )
        
        return True

# Replace
content = content.replace(
    '''async def _validate_current_state_uniqueness(
    db: AsyncSession,
    entity_type: str,
    entity: Any,
    organization_id: str,
) -> bool:
    """Ensure only one current version exists where domain requires it."""
    # Entities that require single current version per organization
    current_state_entities = {
        "CompanyAuthorization": ["approved", "conditional"],
        "CompanyCommitment": ["authorized", "active", "pending_authorization"],
    }
    
    if entity_type not in current_state_entities:
        return True
    
    current_states = current_state_entities[entity_type]
    entity_state = getattr(entity, "state", None)
    
    if entity_state not in current_states:
        return True
    
    # Check if another current version exists
    model = type(entity)
    query = select(model).where(
        model.organization_id == organization_id,
        model.state.in_(current_states),
    )
    
    # Only exclude self if entity has an ID (for updates)
    entity_id = getattr(entity, "id", None)
    if entity_id:
        query = query.where(model.id != entity_id)
    
    existing = await db.execute(query)
    other_current = existing.scalars().first()
    
    if other_current:
        # Allow if the other is the superseded version
        # For CREATE mutations, entity.id may be None (not yet flushed), so don't allow the superseded check to pass
        entity_id = getattr(entity, "id", None)
        if entity_id is not None and getattr(other_current, "superseded_by_id", None) == entity_id:
            return True
        print(f"DEBUG _validate_current_state_uniqueness: about to raise TemporalViolation")
        raise TemporalViolation(
            f"Multiple current {entity_type} states not allowed. "
            f"Existing: {other_current.id} (state: {other_current.state}), "
            f"New: {entity.id if entity_id else 'new'} (state: {entity_state}). "
            f"Use supersession to transition."
        )

    return True''',
    '''    async def _validate_current_state_uniqueness(
        self,
        db: AsyncSession,
        entity_type: str,
        entity: Any,
        organization_id: str,
    ) -> bool:
        """Ensure only one current version exists where domain requires it."""
        # Entities that require single current version per organization
        current_state_entities = {
            "CompanyAuthorization": ["approved", "conditional"],
            "CompanyCommitment": ["authorized", "active", "pending_authorization"],
        }
        
        if entity_type not in current_state_entities:
            return True
        
        current_states = current_state_entities[entity_type]
        entity_state = getattr(entity, "state", None)
        
        if entity_state not in current_states:
            return True
        
        # Check if another current version exists
        model = type(entity)
        query = select(model).where(
            model.organization_id == organization_id,
            model.state.in_(current_states),
        )
        
        # Only exclude self if entity has an ID (for updates)
        entity_id = getattr(entity, "id", None)
        if entity_id:
            query = query.where(model.id != entity_id)
        
        existing = await db.execute(query)
        other_current = existing.scalars().first()
        
        if other_current:
            # Allow if the other is the superseded version
            # For CREATE mutations, entity.id may be None (not yet flushed), so don't allow the superseded check to pass
            entity_id = getattr(entity, "id", None)
            if entity_id is not None and getattr(other_current, "superseded_by_id", None) == entity_id:
                return True
            print(f"DEBUG _validate_current_state_uniqueness: about to raise TemporalViolation")
            raise TemporalViolation(
                f"Multiple current {entity_type} states not allowed. "
                f"Existing: {other_current.id} (state: {other_current.state}), "
                f"New: {entity.id if entity_id else 'new'} (state: {entity_state}). "
                f"Use supersession to transition."
            )
        
        return True''', content)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed _validate_current_state_uniqueness')