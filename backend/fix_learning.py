with open('tests/acceptance/test_backup_restore_roundtrip.py', 'r') as f:
    content = f.read()

# Fix the _create_learning method - use correct OrganizationalLearning fields
old_learning = '''async def _create_learning(self):
        learning = []
        for i in range(2):
            lr = OrganizationalLearning(
                id=self._generate_id("lr-"),
                organization_id=self.org_id,
                lesson_id=f"lesson-{uuid.uuid4().hex[:8]}",
                title=f"Lesson {i}",
                description=f"Lesson {i} description",
                pattern_id=f"pattern-{uuid.uuid4().hex[:8]}",
                evidence_fingerprints=[],
                supporting_event_ids=[],
                contradicting_event_ids=[],
                epistemic_status="confirmed",
                confidence=0.9,
                applicability_scope="company",
                tags=[f"tag{i}"],
                fingerprint=f"{self.org_id}-learning-{i}",
                version=1,
            )
            self.db.add(lr)
            learning.append(lr)
        await self.db.flush()
        self.created_entities["learning"] = [l.id for l in learning]
        return learning'''

new_learning = '''async def _create_learning(self):
        learning = []
        for i in range(2):
            lr = OrganizationalLearning(
                id=self._generate_id("lr-"),
                organization_id=self.org_id,
                kind="lesson",
                fingerprint=f"{self.org_id}-learning-{uuid.uuid4().hex[:8]}",
                title=f"Lesson {i}",
                lesson=f"Lesson {i} description",
                status="confirmed",
                lifecycle="published",
                confidence=0.9,
                source_type="internal",
                source_id=f"source-{uuid.uuid4().hex[:8]}",
                topic_id=f"topic-{uuid.uuid4().hex[:8]}",
                topic_name=f"Topic {i}",
                evidence_json="[]",
                claims_updated_json="[]",
                observation=f"Observation for lesson {i}",
                expectation=f"Expectation for lesson {i}",
                recorded_by=self.caller.employee_id,
                observed_at=utcnow(),
            )
            self.db.add(lr)
            learning.append(lr)
        await self.db.flush()
        self.created_entities["learning"] = [l.id for l in learning]
        return learning'''

content = content.replace(old_learning, new_learning)

with open('tests/acceptance/test_backup_restore_roundtrip.py', 'w') as f:
    f.write(content)

print('Fixed _create_learning')