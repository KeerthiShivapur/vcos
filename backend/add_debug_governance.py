with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add debug to validate_governance
old = '''    # Scope isolation - only check if db is provided
    if target_id and db is not None:
        # Fetch the User object for resolve_accessible_ids
        from app.models.user import User as UserModel
        user_obj = await db.get(UserModel, caller.user_id)
        if not user_obj:
            raise ScopeViolation(f"User {caller.user_id} not found")
        accessible = await resolve_accessible_ids(
            db=db,
            user=user_obj,
            organization_id=caller.organization_id,
            kind=_entity_type_to_kind(target_entity_type),
            ids=[target_id],
        )
        if target_id not in accessible:
            raise ScopeViolation(
                f"Target {target_entity_type}:{target_id} not accessible to caller"
            )'''

new = '''    # Scope isolation - only check if db is provided
    if target_id and db is not None:
        # Fetch the User object for resolve_accessible_ids
        from app.models.user import User as UserModel
        user_obj = await db.get(UserModel, caller.user_id)
        if not user_obj:
            raise ScopeViolation(f"User {caller.user_id} not found")
        print(f"DEBUG validate_governance: target_entity_type={target_entity_type}, target_id={target_id}, user_id={caller.user_id}, user_obj={user_obj}, user_org={user_obj.organization_id if user_obj else None}, caller_org={caller.organization_id}, caller_org_wide={caller.org_wide}")
        accessible = await resolve_accessible_ids(
            db=db,
            user=user_obj,
            organization_id=caller.organization_id,
            kind=_entity_type_to_kind(target_entity_type),
            ids=[target_id],
        )
        print(f"DEBUG validate_governance: accessible={accessible}")
        if target_id not in accessible:
            raise ScopeViolation(
                f"Target {target_entity_type}:{target_id} not accessible to caller"
            )'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added debug to validate_governance')