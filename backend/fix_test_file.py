#!/usr/bin/env python3
"""Fix the test file syntax errors."""

with open('tests/test_gate32_canonical_reliability.py', 'r') as f:
    content = f.read()

# Fix the ExternalUnknownState creation test
old_eus = '''    def test_external_unknown_state_creation(self):
        """Test creating an external unknown state."""
        from app.models.canonical_reliability import ExternalUnknownState
        
        eus = ExternalUnknownState(
            id="eus-1",
            operation_id="op-123",
            organization_id="org-123",
            external_system="stripe",
            external_operation_id="evt_123",
            external_operation_type="payment",
            request_)
        
        assert eus.id == "eus-1"
        assert eus.external_system == "stripe"
        assert eus.state == "unknown"'''

new_eus = '''    def test_external_unknown_state_creation(self):
        """Test creating an external unknown state."""
        from app.models.canonical_reliability import ExternalUnknownState
        
        eus = ExternalUnknownState(
            id="eus-1",
            operation_id="op-123",
            organization_id="org-123",
            external_system="stripe",
            external_operation_id="evt_123",
            external_operation_type="payment",
            request_payload_json={"amount": 100},
            request_fingerprint="fp-123",
        )
        
        assert eus.id == "eus-1"
        assert eus.external_system == "stripe"
        assert eus.state == "unknown"'''

content = content.replace(old_eus, new_eus)

with open('tests/test_gate32_canonical_reliability.py', 'w') as f:
    f.write(content)

print('Fixed test file')