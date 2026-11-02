with open('tests/test_phase_i_longitudinal_company.py', 'r') as f:
    content = f.read()

# Add recorded_at=utcnow() to StrategicOutcome
content = content.replace(
    'source_event_id="test-event",\n            )',
    'source_event_id="test-event",\n        recorded_at=utcnow(),\n    )'
)

with open('tests/test_phase_i_longitudinal_company.py', 'w') as f:
    f.write(content)
print('Done')