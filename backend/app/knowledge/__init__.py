"""Knowledge package exports."""

# Register all submodules to avoid relative import issues
import sys
import importlib.util

_submodules = [
    ("embedding", "embedding.py"),
    ("embeddings", "embeddings.py"),
    ("semantic_search", "semantic_search.py"),
    ("semantic_indexer", "semantic_indexer.py"),
    ("vector_db", "vector_db.py"),
    ("rag_pipeline", "rag_pipeline.py"),
    ("knowledge_base", "knowledge_base.py"),
]

for name, filename in _submodules:
    spec = importlib.util.spec_from_file_location(
        f"app.knowledge.{name}",
        f"D:/vcos1/workspace/vcos/backend/app/knowledge/{filename}"
    )
    if spec:
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"app.knowledge.{name}"] = module
        spec.loader.exec_module(module)

from .embedding import embed_text, cosine, tokenize, keywords, snippet
from .embeddings import (
    get_embedding_provider,
    EmbeddingProvider,
    EmbeddingProviderError,
    DeterministicEmbeddingProvider,
    EmbeddingsApiProvider,
    reset_embedding_provider_for_tests,
    embedding_to_json,
)
from .semantic_search import search
from .semantic_indexer import semantic_indexer
from .vector_db import vector_db_service
from .rag_pipeline import rag_pipeline
from .knowledge_base import (
    kb,
    KINDS,
    KIND_MODELS,
    EXTERNAL_TYPES,
    DEFAULT_CATEGORIES,
    slugify,
    entity_kind_ok,
    resolve_entity,
    load_many,
    kind_label,
    ensure_default_categories,
    get_or_create_tag,
    set_entity_tags,
    entity_tags,
    create_version,
    entity_text,
    write_index,
    delete_index,
    emit_and_audit,
    notify_watchers,
    register_view,
    recent_for_user,
    favorites_for_user,
    published_statuses,
    employee_names,
    parse_keywords,
    now_utc,
)

__all__ = [
    "embed_text",
    "cosine",
    "tokenize",
    "keywords",
    "snippet",
    "get_embedding_provider",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "DeterministicEmbeddingProvider",
    "EmbeddingsApiProvider",
    "reset_embedding_provider_for_tests",
    "embedding_to_json",
    "search",
    "semantic_indexer",
    "vector_db_service",
    "rag_pipeline",
    "kb",
    "KINDS",
    "KIND_MODELS",
    "EXTERNAL_TYPES",
    "DEFAULT_CATEGORIES",
    "slugify",
    "entity_kind_ok",
    "resolve_entity",
    "load_many",
    "kind_label",
    "ensure_default_categories",
    "get_or_create_tag",
    "set_entity_tags",
    "entity_tags",
    "create_version",
    "entity_text",
    "write_index",
    "delete_index",
    "emit_and_audit",
    "notify_watchers",
    "register_view",
    "recent_for_user",
    "favorites_for_user",
    "published_statuses",
    "employee_names",
    "parse_keywords",
    "now_utc",
]