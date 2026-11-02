with open('app/models/company_operating.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add epistemic_status and provenance columns to CompanyDecision
old_decision_end = '''    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class CompanyCausalEdge(Base, TimestampMixin):'''

new_decision_end = '''    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # Gate 6-F: Epistemic integrity - track the epistemic status of the decision
    epistemic_status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)
    # Gate 6-F: Provenance chain for epistemic transitions
    provenance: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


class CompanyCausalEdge(Base, TimestampMixin):'''

content = content.replace(old_decision_end, new_decision_end)

with open('app/models/company_operating.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('Added epistemic_status and provenance columns to CompanyDecision')