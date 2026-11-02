with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix the problematic CompanyAuthorization for delegation
old_code = '''CompanyAuthorization(
            id=self._create_id("auth-"),
            organization_id=self.context.organization_id,
            action="delegate",
            resource_type="project",
            resource_id="test-project",
            decision="allow",
            reason="Test delegation",
            decided_by=self.context.caller.employee_id,
            decided_at=self._now(),
            metadata={"delegated_from": "manager", "delegated_to": "lead"},
        )
        self.context.db.add(delegation)
        await self.context.db.flush()
        
        results.append({
            "type": "delegation",
            "delegation_id": delegation.id,
            "status": "active",
        })
        
        # Revoke it
        delegation.decision = "re'''

new_code = '''CompanyAuthorization(
            id=self._create_id("auth-"),
            organization_id=self.context.organization_id,
            authorization_type="full",
            title="Delegation Authorization",
            description="Test delegation from manager to lead",
            rationale="Test delegation rationale",
            scope_type="project",
            scope_id="test-project",
            decision_id=None,
            commitment_id=None,
            policy_id=None,
            conditions=[],
            constraints={},
            budget_ceiling=None,
            budget_currency="USD",
            valid_from=self._now(),
            valid_until=None,
            state="approved",
            requested_by=self.context.caller.employee_id,
            requested_at=self._now(),
            approved_by=self.context.caller.employee_id,
            approved_at=self._now(),
            evidence_fingerprints=[],
            supporting_pattern_ids=[],
            supporting_lesson_fingerprints=[],
            contradicting_evidence_fingerprints=[],
            contradicting_pattern_ids=[],
            contradiction_ids=[],
            decision_alternative_ids=[],
            decision_evidence_fingerprints=[],
            decision_precedent_ids=[],
            risk_assessment={},
            lesson_fingerprints=[],
            pattern_ids=[],
            source_event_id=f"{self.context.run_id}-delegation",
            source_decision_id=None,
            source_scenario_id=None,
            fingerprint="delegation-fingerprint",
            version=1,
        )
        self.context.db.add(delegation)
        await self.context.db.flush()
        
        results.append({
            "type": "delegation",
            "delegation_id": delegation.id,
            "status": "active",
        })
        
        # Revoke it
        delegation.state = "re'''

content = content.replace(old_code, new_code)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed delegation CompanyAuthorization')