"""Slice 4F.2 — canonical skill taxonomy engine.

One governed taxonomy per tenant, no module invents skills independently.
Equivalence is established ONLY by deterministic rules (a term resolves to a
skill when it is the canonical name or a registered alias of exactly that
skill). Ambiguous claims are surfaced, never merged: when two skills want the
same alias, both owners are flagged ``ambiguous`` and neither silently wins —
governed confirmation must reassign.

Change-driven and bounded: everything a call does is proportional to the
taxonomy size (capped), never to the number of employees.

    * ``ensure_taxonomy``   deterministic starter taxonomy (system_seed),
    * ``create_canonical``  governed skill + alias registration (aliases are
                            tenant-scoped; collisions -> ambiguous, no merge),
    * ``resolve_term``      exact deterministic term -> one skill or None,
    * ``resolve_candidates`` bounded term -> skills matching for evidence
                            extraction (used by the expertise engine),
    * ``get_or_create_for_declared`` canonical skill behind a declared skill,
    * ``bump_person_skill`` PersonSkill upsert (association, not expertise),
    * ``list_taxonomy``     the canonical tree for brain surfaces.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.skills_intelligence import (
    AGGREGATE_SCOPE_TYPES,  # noqa: F401  (re-exported for capability engine)
    CanonicalSkill,
    PersonSkill,
    SkillAlias,
)

logger = logging.getLogger("vcos.people.skills")

MAX_TAXONOMY = 500          # bounded taxonomy per tenant
MAX_ALIASES = 1000          # bounded alias index per tenant
MAX_EXTRACT = 8             # bounded skills extracted per event

# Deterministic starter taxonomy: (name, category, description, aliases, parent).
_SEED: tuple[tuple[str, str, str, tuple[str, ...], Optional[str]], ...] = (
    ("Python", "Programming Languages", "General purpose programming language",
     ("py",), None),
    ("Go", "Programming Languages", "Statically typed systems programming language",
     ("golang",), None),
    ("Rust", "Programming Languages", "Memory-safe systems programming language",
     (), None),
    ("JavaScript", "Programming Languages", "Web and runtime scripting language",
     ("js",), None),
    ("TypeScript", "Programming Languages", "Typed superset of JavaScript",
     ("ts",), None),
    ("SQL", "Databases", "Structured query language for relational data",
     (), None),
    ("PostgreSQL", "Databases", "Open source relational database",
     ("postgres", "pg"), None),
    ("MongoDB", "Databases", "Document oriented NoSQL database",
     ("mongo",), None),
    ("Kubernetes", "Cloud & Infrastructure", "Container orchestration platform",
     ("k8s",), None),
    ("Docker", "Cloud & Infrastructure", "Container runtime and packaging",
     (), None),
    ("AWS", "Cloud & Infrastructure", "Amazon web services cloud platform",
     ("amazon web services",), None),
    ("Terraform", "Cloud & Infrastructure", "Infrastructure as code tool",
     ("tf", "iac"), None),
    ("Deep Learning", "Data & ML", "Neural network based machine learning",
     ("deeplearning",), "Machine Learning"),
    ("PyTorch", "Data & ML", "Deep learning framework",
     (), "Machine Learning"),
    ("TensorFlow", "Data & ML", "Machine learning framework",
     (), "Machine Learning"),
    ("NLP", "Data & ML", "Natural language processing",
     ("natural language processing",), "Machine Learning"),
    ("Computer Vision", "Data & ML", "Image and video understanding",
     ("cv",), "Machine Learning"),
    ("Machine Learning", "Data & ML", "Algorithms that learn from data",
     ("ml",), None),
    ("React", "Web & Frontend", "Component based UI library",
     ("react.js", "reactjs"), None),
    ("Angular", "Web & Frontend", "Application platform and UI framework",
     ("angularjs",), None),
    ("Node.js", "Web & Frontend", "JavaScript runtime",
     ("node", "nodejs"), None),
    ("FastAPI", "Backend", "Python web framework",
     (), None),
    ("Django", "Backend", "Python web framework with batteries",
     (), None),
    ("Distributed Systems", "Backend", "Systems spanning multiple nodes",
     (), None),
    ("Cybersecurity", "Security", "Protecting systems and data from threats",
     ("security", "infosec"), None),
    ("Payments", "Business Domains", "Payment processing and financial systems",
     ("payments architecture",), None),
)


class SkillError(ValueError):
    pass


class SkillEngine:
    # ------------------------------------------------------------------ seed

    async def ensure_taxonomy(
        self, db: AsyncSession, *, organization_id: str
    ) -> int:
        """Idempotent starter taxonomy for a tenant (system_seed)."""
        created = 0
        by_key: dict[str, Optional[CanonicalSkill]] = {}
        for name, category, description, aliases, parent_name in _SEED:
            key = name.lower()
            skill = by_key.get(key)
            if skill is None:
                skill = (
                    await db.execute(
                        select(CanonicalSkill).where(
                            CanonicalSkill.organization_id == organization_id,
                            func.lower(CanonicalSkill.canonical_name) == key,
                        )
                    )
                ).scalar_one_or_none()
            if skill is None:
                skill = CanonicalSkill(
                    organization_id=organization_id,
                    canonical_name=name,
                    description=description,
                    category=category,
                    status="active",
                    provenance="system_seed",
                )
                db.add(skill)
                await db.flush()
                created += 1
            by_key[key] = skill
            for alias in aliases:
                await self._attach_alias(
                    db, organization_id=organization_id, skill=skill,
                    alias=alias, provenance="system_seed",
                )
        # second pass: parent links (the seed tuple may name a parent that
        # sorts later, so links resolve only after every seed row exists)
        for name, _category, _description, _aliases, parent_name in _SEED:
            if parent_name and parent_name.lower() in by_key:
                child = by_key[name.lower()]
                parent = by_key[parent_name.lower()]
                if child is not None and parent is not None:
                    child.parent_skill_id = parent.id
        return created

    # ------------------------------------------------------------------ create

    async def create_canonical(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        category: Optional[str] = None,
        description: Optional[str] = None,
        aliases: Optional[list[str]] = None,
        parent_name: Optional[str] = None,
        provenance: str = "governed",
        created_by: Optional[str] = None,
        aliases_ok: bool = False,
    ) -> CanonicalSkill:
        """Create (or return) a canonical skill under deterministic rules.

        ``aliases_ok=False`` (default) requires every claimed alias to be
        unreserved; a collision raises ``SkillError`` without mutating state.
        ``aliases_ok=True`` registers the non-colliding aliases and flags the
        colliding ones ``ambiguous`` on both owners (never merged).
        """
        canonical = name.strip()
        if not canonical or len(canonical) > 120:
            raise SkillError("canonical skill name is required (<= 120 chars)")
        existing = (
            await db.execute(
                select(CanonicalSkill).where(
                    CanonicalSkill.organization_id == organization_id,
                    func.lower(CanonicalSkill.canonical_name) == canonical.lower(),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        parent: Optional[CanonicalSkill] = None
        if parent_name:
            parent = await self.resolve_term(
                db, organization_id=organization_id, term=parent_name
            )
            if parent is None:
                raise SkillError(f"parent skill '{parent_name}' does not exist")

        skill = CanonicalSkill(
            organization_id=organization_id,
            canonical_name=canonical,
            description=description,
            category=category,
            parent_skill_id=parent.id if parent else None,
            status="active",
            provenance=provenance,
            level=(parent.level + 1) if parent else 0,
            created_by=created_by,
        )
        db.add(skill)
        await db.flush()

        colliding: list[str] = []
        for alias in aliases or []:
            owner = await self._alias_owner(
                db, organization_id=organization_id, term=alias
            )
            if owner is None:
                await self._attach_alias(
                    db, organization_id=organization_id, skill=skill,
                    alias=alias, provenance=provenance, created_by=created_by,
                )
            elif owner.id == skill.id:
                continue
            else:
                colliding.append(alias)
        if colliding and not aliases_ok:
            raise SkillError(
                f"aliases already resolve to another skill: {', '.join(colliding)}"
            )
        return skill

    # ------------------------------------------------------------------ aliases

    async def _alias_owner(
        self, db: AsyncSession, *, organization_id: str, term: str
    ) -> Optional[SkillAlias]:
        key = self.normalize(term)
        if not key:
            return None
        return (
            await db.execute(
                select(SkillAlias).where(
                    SkillAlias.organization_id == organization_id,
                    SkillAlias.alias_lower == key,
                )
            )
        ).scalar_one_or_none()

    async def _attach_alias(
        self,
        db: AsyncSession, *, organization_id: str, skill: CanonicalSkill,
        alias: str, provenance: str = "governed", created_by: Optional[str] = None,
    ) -> tuple[SkillAlias, bool]:
        """Register an alias for a skill. Returns (row, attached)."""
        existing = await self._alias_owner(
            db, organization_id=organization_id, term=alias
        )
        if existing is not None:
            if existing.skill_id == skill.id:
                return existing, True
            # Collision: flag both owners ambiguous — never silently merge.
            note = (
                f"alias '{self.normalize(alias)}' is claimed by more than one "
                f"skill; assign it explicitly to resolve"
            )
            existing.status = "ambiguous"
            existing.note = note
            skill.status = "candidate"
            return existing, False
        row = SkillAlias(
            organization_id=organization_id,
            skill_id=skill.id,
            alias_lower=self.normalize(alias),
            status="active",
            created_by=created_by,
        )
        db.add(row)
        await db.flush()
        return row, True

    # ------------------------------------------------------------------ resolve

    @staticmethod
    def normalize(term: str) -> str:
        return " ".join(term.strip().lower().split())

    async def resolve_term(
        self, db: AsyncSession, *, organization_id: str, term: str
    ) -> Optional[CanonicalSkill]:
        """EXACT deterministic resolution: canonical name first, then a single
        active alias. Returns None when the term is not uniquely resolvable."""
        key = self.normalize(term)
        if not key:
            return None
        row = (
            await db.execute(
                select(CanonicalSkill).where(
                    CanonicalSkill.organization_id == organization_id,
                    func.lower(CanonicalSkill.canonical_name) == key,
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
        alias = (
            await db.execute(
                select(SkillAlias).where(
                    SkillAlias.organization_id == organization_id,
                    SkillAlias.alias_lower == key,
                    SkillAlias.status == "active",
                )
            )
        ).scalars().first()
        if alias is None:
            return None
        return await db.get(CanonicalSkill, alias.skill_id)

    async def resolve_candidates(
        self, db: AsyncSession, *, organization_id: str, terms: list[str],
    ) -> list[CanonicalSkill]:
        """Bounded deterministic term -> skills matching for extraction.

        Rank 3: exact canonical name or alias. Rank 2: substring containment
        (either direction, term length >= 3) against name or aliases. Skills
        are deduplicated, ordered by rank then name, and capped at MAX_EXTRACT.
        """
        terms = [self.normalize(t) for t in terms]
        terms = [t for t in terms if len(t) > 2]
        if not terms:
            return []
        skills = list(
            (
                await db.execute(
                    select(CanonicalSkill).where(
                        CanonicalSkill.organization_id == organization_id,
                        CanonicalSkill.status.in_(("active", "candidate")),
                    ).limit(MAX_TAXONOMY)
                )
            ).scalars().all()
        )
        aliases = list(
            (
                await db.execute(
                    select(SkillAlias).where(
                        SkillAlias.organization_id == organization_id,
                        SkillAlias.status == "active",
                    ).limit(MAX_ALIASES)
                )
            ).scalars().all()
        )
        alias_by_skill: dict[str, list[str]] = {}
        for alias in aliases:
            alias_by_skill.setdefault(alias.skill_id, []).append(alias.alias_lower)

        ranked: list[tuple[int, str, CanonicalSkill]] = []
        seen: set[str] = set()
        exact: dict[str, Optional[CanonicalSkill]] = {}
        for skill in skills:
            names = [self.normalize(skill.canonical_name)]
            names.extend(alias_by_skill.get(skill.id, []))
            for name in names:
                for term in terms:
                    if name == term:
                        key = (3, term, skill)
                    elif (len(term) >= 3 and term in name) or (
                        len(name) >= 3 and name in term
                    ):
                        # precision: an exactly-resolvable term (canonical
                        # name or a registered alias) shadows the loose
                        # containment matches it would otherwise drag in —
                        # "postgresql" must not also match "SQL".
                        if term not in exact:
                            exact[term] = await self.resolve_term(
                                db, organization_id=organization_id, term=term
                            )
                        if exact[term] is not None:
                            continue
                        key = (2, term, skill)
                    else:
                        continue
                    if skill.id in seen:
                        continue
                    seen.add(skill.id)
                    ranked.append((key[0], skill.canonical_name, skill))
                    break
        ranked.sort(key=lambda item: (-item[0], item[1].lower()))
        return [item[2] for item in ranked[:MAX_EXTRACT]]

    # ------------------------------------------------------------------ declared

    async def get_or_create_for_declared(
        self,
        db: AsyncSession, *, organization_id: str, name: str,
        category: Optional[str] = None, description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> CanonicalSkill:
        """Canonical skill behind a user-declared skill name (no aliases are
        invented by the declared source; equivalence via the taxonomy only)."""
        resolved = await self.resolve_term(
            db, organization_id=organization_id, term=name
        )
        if resolved is not None:
            return resolved
        return await self.create_canonical(
            db, organization_id=organization_id, name=name,
            category=category or "Declared", description=description,
            aliases=[], provenance="declared", created_by=created_by,
        )

    async def get_or_create_for_legacy(
        self, db: AsyncSession, *, organization_id: str, name: str,
        category: Optional[str] = None, description: Optional[str] = None,
    ) -> CanonicalSkill:
        """Bridge a legacy operating-layer skill into the canonical taxonomy
        (provenance=legacy_bridge) so the old and canonical worlds share one
        concept space without the operating layer inventing taxonomy."""
        resolved = await self.resolve_term(
            db, organization_id=organization_id, term=name
        )
        if resolved is not None:
            return resolved
        return await self.create_canonical(
            db, organization_id=organization_id, name=name,
            category=category, description=description,
            aliases=[], provenance="legacy_bridge",
        )

    async def bump_person_skill(
        self,
        db: AsyncSession, *, organization_id: str, person_id: str,
        skill_id: str, source: str = "activity",
        declared_level: Optional[int] = None,
        created_by: Optional[str] = None,
    ) -> PersonSkill:
        """Upsert the (person, skill) association with a fresh last_seen.
        Declared rows keep their declared provenance/level; activity only
        advances last_seen."""
        row = (
            await db.execute(
                select(PersonSkill).where(
                    PersonSkill.organization_id == organization_id,
                    PersonSkill.person_id == person_id,
                    PersonSkill.skill_id == skill_id,
                )
            )
        ).scalar_one_or_none()
        now = utcnow()
        if row is None:
            row = PersonSkill(
                organization_id=organization_id,
                person_id=person_id,
                skill_id=skill_id,
                source=source,
                declared_level=declared_level or 2,
                status="active",
                first_seen=now,
                last_seen=now,
                created_by=created_by,
            )
            db.add(row)
            await db.flush()
            return row
        row.last_seen = now
        if row.status != "active":
            row.status = "active"
        if declared_level is not None and row.source in ("declared", "signaled"):
            row.declared_level = declared_level
        await db.flush()
        return row

    # ------------------------------------------------------------------ reads

    async def list_taxonomy(
        self, db: AsyncSession, *, organization_id: str
    ) -> list[dict[str, Any]]:
        """The canonical taxonomy flat list with aliases and parents."""
        skills = list(
            (
                await db.execute(
                    select(CanonicalSkill).where(
                        CanonicalSkill.organization_id == organization_id,
                    ).order_by(CanonicalSkill.category.asc(), CanonicalSkill.canonical_name.asc())
                    .limit(MAX_TAXONOMY)
                )
            ).scalars().all()
        )
        aliases = list(
            (
                await db.execute(
                    select(SkillAlias).where(
                        SkillAlias.organization_id == organization_id,
                    ).limit(MAX_ALIASES)
                )
            ).scalars().all()
        )
        names = {s.id: s.canonical_name for s in skills}
        by_skill: dict[str, list[str]] = {}
        ambiguous: dict[str, list[str]] = {}
        for alias in aliases:
            bucket = ambiguous if alias.status == "ambiguous" else by_skill
            bucket.setdefault(alias.skill_id, []).append(alias.alias_lower)
        return [
            {
                "skill_id": s.id,
                "canonical_name": s.canonical_name,
                "description": s.description,
                "category": s.category,
                "aliases": by_skill.get(s.id, []),
                "ambiguous_aliases": ambiguous.get(s.id, []),
                "parent_skill": names.get(s.parent_skill_id),
                "related_skills": [
                    names.get(rid) for rid in s.related_skill_ids if rid in names
                ],
                "status": s.status,
                "provenance": s.provenance,
                "level": s.level,
            }
            for s in skills
        ]

    async def taxonomy_tree(
        self, db: AsyncSession, *, organization_id: str
    ) -> list[dict[str, Any]]:
        """Bounded parent/child tree of the canonical taxonomy."""
        flat = await self.list_taxonomy(
            db, organization_id=organization_id
        )
        by_id = {f["skill_id"]: f for f in flat}
        roots: list[dict[str, Any]] = []
        for entry in flat:
            node = {**entry, "children": []}
            parent = by_id.get(node["parent_skill"]) if node.get("parent_skill") else None
            pid = parent["skill_id"] if parent else None
            node["parent_skill_id"] = pid
            if pid:
                by_id[pid].setdefault("children", []).append(node)
            else:
                roots.append(node)
        return roots


skill_engine = SkillEngine()