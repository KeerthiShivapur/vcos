"""Industry Solutions & Vertical Intelligence Platform (Phase 17).

The universal VCOS core stays unchanged; every industry is a configurable
pack of modules, templates, workflows, compliance rules, AI profiles and KPIs.
This package hosts the pack definitions (industry/*) and the framework
engines (framework/, marketplace/, analytics/, ai/) that make them plug in.
"""

from app.industry.framework.registry import (  # noqa: F401
    ALL_PACKS,
    all_industries,
    get_industry,
    get_pack,
    list_industry_keys,
    pack,
)
