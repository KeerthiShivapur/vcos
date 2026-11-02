with open('tests/test_gate6e_contradiction_preservation.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Update the test to provide provenance
old = '''        # Attempt to delete contradiction
        # DEBUG: Check accessible IDs
        from app.intelligence.company_context import resolve_accessible_ids
        from app.intelligence.canonical_mutation import _entity_type_to_kind
        kind = _entity_type_to_kind("CompanyDecisionContradiction")
        # Need to get user object for resolve_accessible_ids
        from app.models.user import User as UserModel
        user_obj = await db_session.get(UserModel, caller_a.user_id)
        accessible = await resolve_accessible_ids(
            db=db_session,
            user=user_obj,
            organization_id=test_org_a.id,
            kind=kind,
            ids=[contradiction.id]
        )
        print(f"DEBUG: kind={kind}, contradiction.id={contradiction.id}, accessible={accessible}, org_wide={caller_a.org_wide}")
        
        result = await canonical_delete(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            required_permissions=["commitments:manage"],
        )'''

new = '''        # Attempt to delete contradiction
        # DEBUG: Check accessible IDs
        from app.intelligence.company_context import resolve_accessible_ids
        from app.intelligence.canonical_mutation import _entity_type_to_kind
        kind = _entity_type_to_kind("CompanyDecisionContradiction")
        # Need to get user object for resolve_accessible_ids
        from app.models.user import User as UserModel
        user_obj = await db_session.get(UserModel, caller_a.user_id)
        accessible = await resolve_accessible_ids(
            db=db_session,
            user=user_obj,
            organization_id=test_org_a.id,
            kind=kind,
            ids=[contradiction.id]
        )
        print(f"DEBUG: kind={kind}, contradiction.id={contradiction.id}, accessible={accessible}, org_wide={caller_a.org_wide}")
        
        result = await canonical_delete(
            db=db_session,
            caller=caller_a,
            entity_type="CompanyDecisionContradiction",
            entity_id=contradiction.id,
            required_permissions=["commitments:manage"],
            provenance={"decision_id": decision.id},
        )'''

content = content.replace(old, new)

with open('tests/test_gate6e_contradiction_preservation.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Updated test to provide provenance')