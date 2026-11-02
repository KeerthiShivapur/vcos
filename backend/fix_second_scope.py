with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Fix the second scope check to use _entity_type_to_kind
old = '''            # 2. Target resolution through accessible IDs
            if target_id and target_entity_type not in ["Organization", "User"] and db is not None:
                # Fetch the User object for resolve_accessible_ids
                from app.models.user import User as UserModel
                user_obj = await db.get(UserModel, caller.user_id)
                if not user_obj:
                    raise ScopeViolation(f"User {caller.user_id} not found")
                accessible = await resolve_accessible_ids(
                    db=db,
                    user=user_obj,
                    organization_id=caller.organization_id,
                    kind=target_entity_type.lower().replace("company", "").lower(),
                    ids=[target_id],
                )
                if target_id not in accessible:
                    raise ScopeViolation(
                        f"Target {target_entity_type}:{target_id} not accessible to caller"
                    )'''

new = '''            # 2. Target resolution through accessible IDs
            if target_id and target_entity_type not in ["Organization", "User"] and db is not None:
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

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Fixed second scope check to use _entity_type_to_kind')