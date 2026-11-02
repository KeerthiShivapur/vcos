with open('tests/acceptance/adapters.py', 'r') as f:
    content = f.read()

# Fix CompanyAuthorization creation in governance adapter
old_auth = '''            auth = CompanyAuthorization(
                id=self._create_id("auth-"),
                organization_id=self.context.organization_id,
                policy_id=policy.id,
                subject_id=self.context.caller.employee_id,
                action="approve",
                resource_type=policy.category.lower(),
                resource_id="test-resource",
                decision="allow",
                reason="Test authorization",
                decided_by=self.context.caller.employee_id,
                decided_at=self._now(),
            )'''

new_auth = '''            auth = CompanyAuthorization(
                id=self._create_id("auth-"),
                organization_id=self.context.organization_id,
                authorization_type="full",
                title=f"Authorization for {policy.name}",
                description="Test authorization",
                rationale="Test authorization rationale",
                scope_type="organization",
                scope_id=self.context.organization_id,
                decision_intelligence_context_id=None,
                decision_id=None,
                commitment_id=None,
                policy_id=policy.id,
                conditions={},
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
                source_event_id=self.context.run_id,
                source_decision_id=None,
                source_scenario_id=None,
                fingerprint=None,
                version=1,
            )'''

content = content.replace(old_auth, new_auth)

with open('tests/acceptance/adapters.py', 'w') as f:
    f.write(content)

print('Fixed CompanyAuthorization creation')