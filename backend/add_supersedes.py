with open('app/models/company_operating.py', 'r') as f:
    content = f.read()

# Add supersedes_id field after source_event_id
old = '''    # event that surfaced the contradiction (exact-once)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)


class CompanyScenarioRun(Base, TimestampMixin):'''

new = '''    # event that surfaced the contradiction (exact-once)
    source_event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # supersedes relationship for contradiction lineage preservation
    supersedes_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_decision_contradictions.id", ondelete="SET NULL"), default=None
    )
    supersedes: Mapped[Optional["CompanyDecisionContradiction"]] = relationship(
        "CompanyDecisionContradiction", remote_side=[id], backref="superseded_by"
    )


class CompanyScenarioRun(Base, TimestampMixin):'''

content = content.replace(old, new)

with open('app/models/company_operating.py', 'w') as f:
    f.write(content)

print('Added supersedes_id field to CompanyDecisionContradiction')