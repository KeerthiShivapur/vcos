with open('create_company_state.py', 'r') as f:
    content = f.read()

# Fix CanonicalObservation fields
old_obs = '''            obs1 = CanonicalObservation(
                organization_id=org.id,
                observation_type="platform_metric",
                title="Platform latency within SLA",
                description="API latency is within SLA thresholds",
                source_subsystem="platform_metrics",
                epistemic_state="observed",
                confidence=0.95,
                recorded_at=utcnow(),
                observation_data={"metric": "api_latency", "value": 50, "unit": "ms"},
                fingerprint=f"obs-{uuid.uuid4().hex[:16]}"
            )'''

new_obs = '''            obs1 = CanonicalObservation(
                organization_id=org.id,
                observation_type="health_check",
                title="Platform latency within SLA",
                description="API latency is within SLA thresholds",
                source="platform_metrics",
                source_component="api_gateway",
                epistemic_status="observed",
                severity="info",
                recorded_at=utcnow(),
                observed_at=utcnow(),
                details_json={"metric": "api_latency", "value": 50, "unit": "ms"},
                fingerprint=f"obs-{uuid.uuid4().hex[:16]}"
            )'''

content = content.replace(old_obs, new_obs)

with open('create_company_state.py', 'w') as f:
    f.write(content)
print('Fixed CanonicalObservation fields')