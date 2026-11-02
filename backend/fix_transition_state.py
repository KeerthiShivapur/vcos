with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix canonical_transition to use 'status' for contradiction entities
old = '''    async def transition_fn(db: AsyncSession):
        # Re-fetch entity in the mutation transaction
        entity = await db.get(model, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

        # Validate state transition
        validate_state_transition(entity_type, entity.state, new_state)

        old_state = entity.state
        entity.state = new_state'''

new = '''    # Determine the state field name for this entity type
    state_field = "status" if entity_type in ("CompanyDecisionContradiction", "ObjectiveContradiction") else "state"

    async def transition_fn(db: AsyncSession):
        # Re-fetch entity in the mutation transaction
        entity = await db.get(model, entity_id)
        if not entity:
            raise ValueError(f"Entity not found: {entity_type}:{entity_id}")

        # Validate state transition
        current_state = getattr(entity, state_field)
        validate_state_transition(entity_type, current_state, new_state)

        old_state = current_state
        setattr(entity, state_field, new_state)'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed canonical_transition to use status for contradictions')