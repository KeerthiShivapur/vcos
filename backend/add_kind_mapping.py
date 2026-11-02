with open('app/intelligence/canonical_mutation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add the mapping for entity types to evidence kinds
old = '''async def validate_governance(
    db: AsyncSession,
    caller: CallerAccess,
    target_entity_type: str,
    target_id: Optional[str] = None,
    target_organization_id: Optional[str] = None,
    required_permissions: Optional[list[str]] = None,
) -> bool:
    """Validate governance rules for a mutation.

    Reuses existing governance primitives from company_context.py and governance_service.
    """
    # Tenant isolation
    if target_organization_id and target_organization_id != caller.organization_id:
        raise TenantIsolationViolation(
            f"Cross-tenant mutation denied: caller org {caller.organization_id} "
            f"cannot mutate org {target_organization_id}"
        )

    # Scope isolation - only check if db is provided
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
            kind=target_entity_type.lower().replace("company", "").lower(),
            ids=[target_id],
        )'''

new = '''# Entity type to evidence kind mapping for scope checks
_ENTITY_TYPE_TO_KIND = {
    "CompanyDecisionContradiction": "decision_contradiction",
    "ObjectiveContradiction": "objective_contradiction",
    "CompanyDecisionAlternative": "decision",
    "CompanyAuthorization": "authorization",
    "CompanyCommitment": "commitment",
    "CompanyAction": "action",
    "CompanyGoal": "goal",
    "CompanyObjective": "goal",
    "CompanyInitiative": "project",
    "CompanyIntent": "project",
    "Project": "project",
}

def _entity_type_to_kind(entity_type: str) -> str:
    """Convert entity type to evidence kind for scope checks."""
    return _ENTITY_TYPE_TO_KIND.get(entity_type, entity_type.lower().replace("company", "").lower())


async def validate_governance(
    db: AsyncSession,
    caller: CallerAccess,
    target_entity_type: str,
    target_id: Optional[str] = None,
    target_organization_id: Optional[str] = None,
    required_permissions: Optional[list[str]] = None,
) -> bool:
    """Validate governance rules for a mutation.

    Reuses existing governance primitives from company_context.py and governance_service.
    """
    # Tenant isolation
    if target_organization_id and target_organization_id != caller.organization_id:
        raise TenantIsolationViolation(
            f"Cross-tenant mutation denied: caller org {caller.organization_id} "
            f"cannot mutate org {target_organization_id}"
        )

    # Scope isolation - only check if db is provided
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
        )'''

content = content.replace(old, new)

with open('app/intelligence/canonical_mutation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added entity type to kind mapping')