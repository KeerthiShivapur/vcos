"""Phase 9 — Background Intelligence & Autonomous Organization engines."""

from app.intelligence.burnout_engine import burnout_engine  # noqa: F401
from app.intelligence.collaboration_engine import collaboration_engine  # noqa: F401
from app.intelligence.duplicate_engine import duplicate_engine  # noqa: F401
from app.intelligence.expertise_engine import expertise_engine  # noqa: F401
from app.intelligence.graph_engine import graph_engine  # noqa: F401
from app.intelligence.insights_engine import insights_engine  # noqa: F401
from app.intelligence.knowledge_engine import knowledge_engine  # noqa: F401
from app.intelligence.learning_engine import learning_engine  # noqa: F401
from app.intelligence.pattern_engine import pattern_engine  # noqa: F401
from app.intelligence.recommendation_engine import recommendation_engine  # noqa: F401
from app.intelligence.search_engine import search_engine  # noqa: F401
from app.intelligence.workflow_engine import workflow_engine  # noqa: F401

__all__ = [
    "expertise_engine",
    "graph_engine",
    "knowledge_engine",
    "search_engine",
    "collaboration_engine",
    "burnout_engine",
    "duplicate_engine",
    "pattern_engine",
    "learning_engine",
    "workflow_engine",
    "recommendation_engine",
    "insights_engine",
]
