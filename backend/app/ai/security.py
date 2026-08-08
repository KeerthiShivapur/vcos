"""Phase 7.14 — AI security helpers.

Defense in depth on top of the existing permission layer:

  * PII redaction for outbound context (emails/phones replaced before any
    external provider call), while rule-based answers keep full fidelity.
  * Confirmation markers: the action engine only fires on explicit intent.
  * The gateway's own safety filter (blocked phrases) stays as the last line.

The router enforces ``ai:use``; action execution additionally checks the
action-specific permission (``tasks:manage`` etc.).
"""

from __future__ import annotations

import re
from typing import Any

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_PHONE = re.compile(r"(?<!\d)(?:\+?\d{1,3}[ -]?)?\(?\d{3}\)?[ -]?\d{3}[ -]?\d{4}(?!\d)")


def redact(text: str) -> str:
    if not text:
        return text
    text = _EMAIL.sub("[email]", text)
    text = _PHONE.sub("[phone]", text)
    return text


def redact_payload(payload: dict[str, Any], sensitive_keys: tuple[str, ...] = ("email", "phone", "token", "api_key")) -> dict[str, Any]:
    out = {}
    for key, value in payload.items():
        if key in sensitive_keys and isinstance(value, str):
            out[key] = "[redacted]"
        elif isinstance(value, dict):
            out[key] = redact_payload(value, sensitive_keys)
        else:
            out[key] = value
    return out


CONFIRMATION_PHRASES = ("yes", "go ahead", "please do", "confirm", "sure", "create it", "do it", "ok", "okay", "please")


def requires_confirmation(action_type: str) -> bool:
    return action_type in ("schedule_meeting", "update_task_status", "remember")
