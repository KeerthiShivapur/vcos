"""Shared integrity guards for work-domain services.

Every update path funnels through apply_editable() so tenant identity and
record identity can never be mutated via PATCH bodies, and unknown fields
are rejected instead of silently accepted or dropped.
"""

from typing import Any

IMMUTABLE_FIELDS = ("id", "organization_id", "created_at", "updated_at")


def apply_editable(obj: Any, data: dict[str, Any]) -> list[str]:
    """Apply only mutable fields that exist on the object.

    Returns the keys applied. Immutable identity/tenant fields and unknown
    fields raise ValueError so a raw PATCH can never mutate organization_id
    or smuggle a reference the model does not actually support.
    """
    applied: list[str] = []
    for key, value in data.items():
        if key in IMMUTABLE_FIELDS:
            raise ValueError(f"Field is not editable: {key}")
        if not hasattr(obj, key):
            raise ValueError(f"Unsupported field: {key}")
        setattr(obj, key, value)
        applied.append(key)
    return applied
