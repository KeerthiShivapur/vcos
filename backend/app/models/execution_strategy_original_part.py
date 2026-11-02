class CompanyGoal(Base, TimestampMixin):
    """One company goal - the top of the strategic execution graph."""

    __tablename__ = "company_goals"
    __table_args__ = (
        Index("ix_cg_org_status", "organization_id", "status"),
        Index("ix_cg_org_priority", "organization_id", "priority"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # revenue | expansion | efficiency | security | retention | growth | other
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # 1 (highest) .. 5 (lowest)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    # the outcome the goal chases (bounded, evidence-optional)
    metric_kind: Mapped[Optional[str]] = mapped_column(String(80), default=None)
    metric_unit: Mapped[Optional[str]] = mapped_column(String(40), default=None)
    target_value: Mapped[Optional[float]] = mapped_column(Float, default=None)
    current_value: Mapped[Optional[float]] = mapped_column(Float, default=None)
    owner_person_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    owner_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    timeline_label: Mapped[str] = mapped_column(String(120), nullable=False, default="")


class CompanyObjective(Base, TimestampMixin):
    """One objective under a company goal - the goal's operational intent."""

    __tablename__ = "company_objectives"
    __table_args__ = (Index("ix_coj_org_goal", "organization_id", "goal_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("company_goals.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # canonical capability names the objective requires to execute
    required_capabilities: Mapped[Optional[list]] = mapped_column(JSON)
    owner_person_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    owner_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class CompanyInitiative(Base, TimestampMixin):
    """One initiative under an objective - the strategic ask on execution.

    Carries the strategic assumption (expected outcome) and, where declared,
    customer commitments. These are the two edges that make strategy
    measurable: outcome.recorded closes the assumption later.
    """

    __tablename__ = "company_initiatives"
    __table_args__ = (Index("ix_ci_org_obj", "organization_id", "objective_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    objective_id: Mapped[str] = mapped_column(
        ForeignKey("company_objectives.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    required_capabilities: Mapped[Optional[list]] = mapped_column(JSON)
    # declared human commitments, e.g. [{"customer": "ACME", "summary": "launch by Q3"}]
    customer_commitments: Mapped[Optional[list]] = mapped_column(JSON)
    # the strategic assumption: {metric_kind, target_value, unit}
    expected_outcome: Mapped[Optional[dict]] = mapped_column(JSON)
    owner_person_id: Mapped[Optional[str]] = mapped_column(String(64), default=None)
    owner_label: Mapped[str] = mapped_column(String(255), nullable=False, default="")


class StrategicLink(Base, TimestampMixin):
    """Goal -> work traceability: one initiative <-> project link.

    Both constraint layers are exact-once: one live link per (org,
    initiative, project) and one row per (org, initiative, project, event)
    so replays of strategy.initiative.linked converge to the same row.
    """

    __tablename__ = "strategic_links"
    __table_args__ = (
        Index("ix_sl_org_init", "organization_id", "initiative_id"),
        Index("ix_sl_org_project", "organization_id", "project_id"),
        UniqueConstraint(
            "organization_id", "initiative_id", "project_id",
            name="uq_sl_live_link",
        ),
        UniqueConstraint(
            "organization_id", "initiative_id", "project_id", "source_event_id",
            name="uq_sl_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("company_initiatives.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategicHistory(Base, TimestampMixin):
    """Append-only temporal trail of strategic changes (organizational memory).

    One row per (entity, field, event): e.g. a goal's priority moving 3 -> 2
    with the reason a human recorded. Replays are exact-once.
    """

    __tablename__ = "strategic_history"
    __table_args__ = (
        Index("ix_sh_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_sh_org_time", "organization_id", "changed_at"),
        UniqueConstraint(
            "organization_id", "entity_type", "entity_id", "field", "source_event_id",
            name="uq_sh_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)  # goal|objective|initiative
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    new_value: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategicOutcome(Base, TimestampMixin):
    """One recorded strategy -> outcome observation (expected vs actual).

    Links an initiative's strategic assumption to a measured reality later.
    Exact-once on (org, initiative, source_event) - replay never double
    counts. Used by the learning engine to estimate the organization's
    optimism bias per metric kind.
    """

    __tablename__ = "strategic_outcomes"
    __table_args__ = (
        Index("ix_so_org_init", "organization_id", "initiative_id"),
        UniqueConstraint(
            "organization_id", "initiative_id", "source_event_id",
            name="uq_so_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    initiative_id: Mapped[str] = mapped_column(
        ForeignKey("company_initiatives.id", ondelete="CASCADE"), nullable=False
    )
    initiative_label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    project_id: Mapped[Optional[str]] = mapped_column(String(32), default=None)
    project_label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    metric_kind: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    expected_value: Mapped[Optional[float]] = mapped_column(Float, default=None)
    actual_value: Mapped[Optional[float]] = mapped_column(Float, default=None)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class StrategicSnapshot(Base, TimestampMixin):
    """One persisted strategic recompute of a goal's neighborhood.

    The incremental guarantee: an event refreshes ONLY the affected goal and
    writes one snapshot row keyed by (org, goal, event) - replays converge.
    The payload is the full evidence-backed assessment served by the brain.
    """

    __tablename__ = "strategic_snapshots"
    __table_args__ = (
        Index("ix_ss_org_goal_time", "organization_id", "goal_id", "occurred_at"),
        UniqueConstraint(
            "organization_id", "goal_id", "source_event_id",
            name="uq_ss_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("company_goals.id", ondelete="CASCADE"), nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    event_name: Mapped[str] = mapped_column(String(60), nullable=False)
    coverage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health: Mapped[str] = mapped_column(String(16), nullable=False, default="critical")
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )