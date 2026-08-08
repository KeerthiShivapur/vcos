"""Phase 7.2 — AI memory system.

Five cognitive memory stores backed by the ``ai_memories`` table plus an
in-process working memory ring buffer:

  working         recent context for active conversations (no DB)
  episodic        what happened (events, experiences, meeting outcomes)
  semantic        what is true (facts, preferences, decisions)
  procedural      how work happens (sops, playbooks, recipes)
  organizational  how the company works (structure, roles, norms, culture)

Use the top-level :class:`MemoryManager` (``memory_manager`` singleton) as the
single facade: it routes writes/reads to the right store and handles
consolidation from working memory into durable memory.
"""

from app.ai.memory.memory_manager import MemoryManager, memory_manager

__all__ = ["MemoryManager", "memory_manager"]
