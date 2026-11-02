with open('tests/acceptance/test_release_candidate_slice_2a.py', 'r') as f:
    content = f.read()

# Fix HealthDimension creation to include fingerprint
old = '''# Create health dimension
        health = HealthDimension(
            organization_id=org.id,
            dimension="api_latency",
            status="healthy",
            current_value=50.0,
            target_value=100.0,
            recorded_at=datetime.now(timezone.utc),
        )
        pg_db_session.add(health)'''

new = '''# Create health dimension
        import hashlib
        fingerprint = hashlib.sha256(f"api_latency|{org.id}|company|".encode()).hexdigest()[:64]
        health = HealthDimension(
            organization_id=org.id,
            dimension="api_latency",
            scope_type="company",
            scope_id=None,
            status="healthy",
            current_value=50.0,
            target_value=100.0,
            recorded_at=datetime.now(timezone.utc),
            fingerprint=fingerprint,
        )
        pg_db_session.add(health)'''

content = content.replace(old, new)

# Fix the second occurrence
old2 = '''# Create health for both
        health1 = HealthDimension(organization_id=org1.id, dimension="test", status="healthy", current_value=10, target_value=20, recorded_at=datetime.now(timezone.utc))
        health2 = HealthDimension(organization_id=org2.id, dimension="test", status="healthy", current_value=10, target_value=20, recorded_at=datetime.now(timezone.utc))'''

new2 = '''# Create health for both
        import hashlib
        fingerprint1 = hashlib.sha256(f"test|{org1.id}|company|".encode()).hexdigest()[:64]
        fingerprint2 = hashlib.sha256(f"test|{org2.id}|company|".encode()).hexdigest()[:64]
        health1 = HealthDimension(organization_id=org1.id, dimension="test", scope_type="company", status="healthy", current_value=10, target_value=20, recorded_at=datetime.now(timezone.utc), fingerprint=fingerprint1)
        health2 = HealthDimension(organization_id=org2.id, dimension="test", scope_type="company", status="healthy", current_value=10, target_value=20, recorded_at=datetime.now(timezone.utc), fingerprint=fingerprint2)'''

content = content.replace(old2, new2)

with open('tests/acceptance/test_release_candidate_slice_2a.py', 'w') as f:
    f.write(content)
print('Done')