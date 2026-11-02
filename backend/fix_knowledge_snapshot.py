with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix CompanyKnowledgeSnapshot fields
old_ks = '''            ks1 = CompanyKnowledgeSnapshot(
                organization_id=org.id,
                snapshot_id=f"ks-{uuid.uuid4().hex[:8]}",
                claim_id=f"claim-{uuid.uuid4().hex[:8]}",
                claim_type="platform_status",
                claim_summary="Platform migration to PostgreSQL 18 is in progress",
                epistemic_state="observed",
                confidence=0.85,
                evidence_json={"source": "platform_metrics", "timestamp": utcnow().isoformat()},
                snapshot_at=utcnow(),
                valid_from=utcnow(),
                valid_to=utcnow() + timedelta(days=30),
                recorded_by=admin_user.id
            )'''

new_ks = '''            ks1 = CompanyKnowledgeSnapshot(
                organization_id=org.id,
                claim_id=f"claim-{uuid.uuid4().hex[:8]}",
                claim_type="platform_status",
                claim_version=1,
                epistemic_state="observed",
                confidence=0.85,
                belief_json={"summary": "Platform migration to PostgreSQL 18 is in progress"},
                evidence_ids_json=["platform_metrics"],
                contradiction_ids_json=[],
                snapshot_at=utcnow(),
                valid_from=utcnow(),
                valid_to=utcnow() + timedelta(days=30),
                recorded_by=admin_user.id
            )'''

content = content.replace(old_ks, new_ks)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed CompanyKnowledgeSnapshot fields')