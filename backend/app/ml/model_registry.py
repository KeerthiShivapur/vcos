"""
Model Registry for VCOS ML Platform.

MLflow-compatible model registry with:
- Model versioning
- Stage management (Staging, Production, Archived)
- Model artifacts storage
- Model lineage tracking
- Deployment tracking
"""

import asyncio
import hashlib
import json
import logging
import os
import shutil
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, BinaryIO
from uuid import uuid4

import asyncpg

from app.core.config import settings

logger = logging.getLogger(__name__)


class ModelStage(str, Enum):
    """Model lifecycle stages."""
    NONE = "none"
    STAGING = "staging"
    PRODUCTION = "production"
    ARCHIVED = "archived"


class ModelStatus(str, Enum):
    """Model status."""
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    DEPRECATED = "deprecated"


@dataclass
class ModelArtifact:
    """Model artifact reference."""
    path: str
    size_bytes: int
    checksum: str
    artifact_type: str  # model, tokenizer, config, etc.
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelSignature:
    """Model input/output signature."""
    inputs: List[Dict[str, Any]]  # [{"name": "...", "type": "...", "shape": [...]}]
    outputs: List[Dict[str, Any]]
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelVersion:
    """Model version with metadata."""
    name: str
    version: int
    stage: ModelStage = ModelStage.NONE
    status: ModelStatus = ModelStatus.PENDING

    # Source info
    run_id: str = ""
    experiment_id: str = ""
    source: str = ""  # Path or URI to model artifacts

    # Artifacts
    artifacts: List[ModelArtifact] = field(default_factory=list)

    # Signature
    signature: Optional[ModelSignature] = None

    # Metadata
    description: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    params: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)

    # Timestamps
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""

    # Lineage
    parent_version: Optional[int] = None
    dataset_version: str = ""


@dataclass
class RegisteredModel:
    """Registered model with versions."""
    name: str
    description: str = ""
    tags: Dict[str, str] = field(default_factory=dict)
    versions: List[ModelVersion] = field(default_factory=list)
    latest_version: int = 0
    production_version: Optional[int] = None
    staging_version: Optional[int] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ModelDeployment:
    """Model deployment tracking."""
    id: str
    model_name: str
    model_version: int
    endpoint_name: str
    endpoint_url: str
    status: str  # deploying, running, stopped, failed
    replicas: int = 1
    resources: Dict[str, Any] = field(default_factory=dict)
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    health_check_url: str = ""
    metrics: Dict[str, Any] = field(default_factory=dict)


class ArtifactStore(ABC):
    """Abstract artifact storage."""

    @abstractmethod
    async def save(self, model_name: str, version: int, artifacts: List[ModelArtifact]) -> List[str]:
        pass

    @abstractmethod
    async def load(self, model_name: str, version: int) -> List[ModelArtifact]:
        pass

    @abstractmethod
    async def delete(self, model_name: str, version: int):
        pass


class LocalArtifactStore(ArtifactStore):
    """Local filesystem artifact store."""

    def __init__(self, base_path: str = "./mlflow_artifacts"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_model_dir(self, model_name: str, version: int) -> Path:
        return self.base_path / model_name / str(version)

    async def save(self, model_name: str, version: int, artifacts: List[ModelArtifact]) -> List[str]:
        model_dir = self._get_model_dir(model_name, version)
        model_dir.mkdir(parents=True, exist_ok=True)

        saved_paths = []
        for artifact in artifacts:
            src = Path(artifact.path)
            if not src.exists():
                logger.warning(f"Artifact not found: {artifact.path}")
                continue

            dst = model_dir / artifact.artifact_type / src.name
            dst.parent.mkdir(parents=True, exist_ok=True)

            if src.is_dir():
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)

            saved_paths.append(str(dst))

        # Save metadata
        metadata = {
            "model_name": model_name,
            "version": version,
            "artifacts": [
                {
                    "path": str(a.path),
                    "size_bytes": a.size_bytes,
                    "checksum": a.checksum,
                    "artifact_type": a.artifact_type,
                    "metadata": a.metadata,
                }
                for a in artifacts
            ],
            "saved_at": datetime.utcnow().isoformat(),
        }
        with open(model_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        return saved_paths

    async def load(self, model_name: str, version: int) -> List[ModelArtifact]:
        model_dir = self._get_model_dir(model_name, version)
        metadata_file = model_dir / "metadata.json"

        if not metadata_file.exists():
            return []

        with open(metadata_file) as f:
            metadata = json.load(f)

        artifacts = []
        for a in metadata.get("artifacts", []):
            artifacts.append(ModelArtifact(
                path=a["path"],
                size_bytes=a["size_bytes"],
                checksum=a["checksum"],
                artifact_type=a["artifact_type"],
                metadata=a.get("metadata", {}),
            ))

        return artifacts

    async def delete(self, model_name: str, version: int):
        model_dir = self._get_model_dir(model_name, version)
        if model_dir.exists():
            shutil.rmtree(model_dir)


class PostgresModelRegistry:
    """PostgreSQL-backed model registry."""

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._pool: Optional[asyncpg.Pool] = None

    async def initialize(self):
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=5,
            max_size=20,
        )
        await self._ensure_tables()
        logger.info("PostgreSQL model registry initialized")

    async def _ensure_tables(self):
        async with self._pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS registered_models (
                    name TEXT PRIMARY KEY,
                    description TEXT DEFAULT '',
                    tags JSONB DEFAULT '{}',
                    latest_version INTEGER DEFAULT 0,
                    production_version INTEGER,
                    staging_version INTEGER,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS model_versions (
                    name TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    stage TEXT DEFAULT 'none',
                    status TEXT DEFAULT 'pending',
                    run_id TEXT DEFAULT '',
                    experiment_id TEXT DEFAULT '',
                    source TEXT DEFAULT '',
                    artifacts JSONB DEFAULT '[]',
                    signature JSONB,
                    description TEXT DEFAULT '',
                    tags JSONB DEFAULT '{}',
                    params JSONB DEFAULT '{}',
                    metrics JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    created_by TEXT DEFAULT '',
                    parent_version INTEGER,
                    dataset_version TEXT DEFAULT '',
                    PRIMARY KEY (name, version)
                )
            """)

            await conn.execute("""
                CREATE TABLE IF NOT EXISTS model_deployments (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    model_name TEXT NOT NULL,
                    model_version INTEGER NOT NULL,
                    endpoint_name TEXT NOT NULL,
                    endpoint_url TEXT NOT NULL,
                    status TEXT DEFAULT 'deploying',
                    replicas INTEGER DEFAULT 1,
                    resources JSONB DEFAULT '{}',
                    config JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW(),
                    health_check_url TEXT DEFAULT '',
                    metrics JSONB DEFAULT '{}'
                )
            """)

            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_model_versions_name_stage 
                ON model_versions (name, stage)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_deployments_model 
                ON model_deployments (model_name, model_version)
            """)

    async def close(self):
        if self._pool:
            await self._pool.close()

    # ==================== Model Management ====================

    async def create_model(self, name: str, description: str = "", tags: Dict[str, str] = {}) -> RegisteredModel:
        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO registered_models (name, description, tags)
                VALUES ($1, $2, $3)
                ON CONFLICT (name) DO UPDATE SET
                    description = EXCLUDED.description,
                    tags = EXCLUDED.tags,
                    updated_at = NOW()
            """, name, description, json.dumps(tags))

        return await self.get_model(name)

    async def get_model(self, name: str) -> Optional[RegisteredModel]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM registered_models WHERE name = $1
            """, name)

            if not row:
                return None

            # Load versions
            version_rows = await conn.fetch("""
                SELECT * FROM model_versions WHERE name = $1 ORDER BY version DESC
            """, name)

            versions = [self._row_to_version(r) for r in version_rows]

            production_version = None
            staging_version = None
            for v in versions:
                if v.stage == ModelStage.PRODUCTION:
                    production_version = v.version
                elif v.stage == ModelStage.STAGING:
                    staging_version = v.version

            return RegisteredModel(
                name=row["name"],
                description=row["description"],
                tags=row["tags"] or {},
                versions=versions,
                latest_version=row["latest_version"],
                production_version=production_version,
                staging_version=staging_version,
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )

    async def list_models(self, filter_tags: Dict[str, str] = {}) -> List[RegisteredModel]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT name FROM registered_models")
            models = []
            for row in rows:
                model = await self.get_model(row["name"])
                if model:
                    # Filter by tags
                    match = all(model.tags.get(k) == v for k, v in filter_tags.items())
                    if match or not filter_tags:
                        models.append(model)
            return models

    async def delete_model(self, name: str):
        async with self._pool.acquire() as conn:
            await conn.execute("DELETE FROM model_versions WHERE name = $1", name)
            await conn.execute("DELETE FROM registered_models WHERE name = $1", name)

    # ==================== Version Management ====================

    async def create_version(
        self,
        name: str,
        version: Optional[int] = None,
        run_id: str = "",
        experiment_id: str = "",
        source: str = "",
        description: str = "",
        tags: Dict[str, str] = {},
        params: Dict[str, Any] = {},
        metrics: Dict[str, float] = {},
        signature: Optional[ModelSignature] = None,
        parent_version: Optional[int] = None,
        dataset_version: str = "",
        created_by: str = "",
    ) -> ModelVersion:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Get next version number
                if version is None:
                    row = await conn.fetchrow("""
                        SELECT COALESCE(MAX(version), 0) + 1 FROM model_versions WHERE name = $1
                    """, name)
                    version = row[0]

                # Insert version
                await conn.execute("""
                    INSERT INTO model_versions (
                        name, version, stage, status, run_id, experiment_id, source,
                        artifacts, signature, description, tags, params, metrics,
                        created_by, parent_version, dataset_version
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $10, $11, $12, $13, $14, $15)
                """, name, version, ModelStage.NONE.value, ModelStatus.READY.value,
                    run_id, experiment_id, source,
                    json.dumps([]),
                    json.dumps(signature.__dict__) if signature else None,
                    description, json.dumps(tags), json.dumps(params), json.dumps(metrics),
                    created_by, parent_version, "")

                # Update registered model
                await conn.execute("""
                    UPDATE registered_models 
                    SET latest_version = $1, updated_at = NOW()
                    WHERE name = $2
                """, version, name)

        return await self.get_version(name, version)

    async def get_version(self, name: str, version: int) -> Optional[ModelVersion]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT * FROM model_versions WHERE name = $1 AND version = $2
            """, name, version)

            if not row:
                return None

            return self._row_to_version(row)

    async def get_latest_version(self, name: str, stage: Optional[ModelStage] = None) -> Optional[ModelVersion]:
        async with self._pool.acquire() as conn:
            if stage:
                row = await conn.fetchrow("""
                    SELECT * FROM model_versions 
                    WHERE name = $1 AND stage = $2 
                    ORDER BY version DESC LIMIT 1
                """, name, stage.value)
            else:
                row = await conn.fetchrow("""
                    SELECT * FROM model_versions WHERE name = $1 ORDER BY version DESC LIMIT 1
                """, name)

            if not row:
                return None
            return self._row_to_version(row)

    async def list_versions(self, name: str) -> List[ModelVersion]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM model_versions WHERE name = $1 ORDER BY version DESC
            """, name)
            return [self._row_to_version(r) for r in rows]

    async def transition_stage(self, name: str, version: int, stage: ModelStage):
        """Transition model version to a new stage."""
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # Get current stage
                current = await conn.fetchrow("""
                    SELECT stage FROM model_versions WHERE name = $1 AND version = $2
                """, name, version)

                if not current:
                    raise ValueError(f"Model version not found: {name}/{version}")

                old_stage = ModelStage(current["stage"])

                # Archive any existing model in target stage
                if stage in [ModelStage.STAGING, ModelStage.PRODUCTION]:
                    await conn.execute("""
                        UPDATE model_versions 
                        SET stage = $1, updated_at = NOW()
                        WHERE name = $2 AND stage = $3 AND version != $4
                    """, ModelStage.ARCHIVED.value, name, stage.value, version)

                # Update new version
                await conn.execute("""
                    UPDATE model_versions 
                    SET stage = $1, updated_at = NOW()
                    WHERE name = $2 AND version = $3
                """, stage.value, name, version)

                # Update registered model pointers
                if stage == ModelStage.PRODUCTION:
                    await conn.execute("""
                        UPDATE registered_models SET production_version = $1 WHERE name = $2
                    """, version, name)
                elif stage == ModelStage.STAGING:
                    await conn.execute("""
                        UPDATE registered_models SET staging_version = $1 WHERE name = $2
                    """, version, name)

    async def add_artifacts(self, name: str, version: int, artifacts: List[ModelArtifact]):
        async with self._pool.acquire() as conn:
            artifacts_json = json.dumps([
                {
                    "path": a.path,
                    "size_bytes": a.size_bytes,
                    "checksum": a.checksum,
                    "artifact_type": a.artifact_type,
                    "metadata": a.metadata,
                }
                for a in artifacts
            ])
            await conn.execute("""
                UPDATE model_versions SET artifacts = $1, updated_at = NOW()
                WHERE name = $2 AND version = $3
            """, artifacts_json, name, version)

    async def set_signature(self, name: str, version: int, signature: ModelSignature):
        async with self._pool.acquire() as conn:
            await conn.execute("""
                UPDATE model_versions SET signature = $1, updated_at = NOW()
                WHERE name = $2 AND version = $3
            """, json.dumps(signature.__dict__), name, version)

    def _row_to_version(self, row) -> ModelVersion:
        return ModelVersion(
            name=row["name"],
            version=row["version"],
            stage=ModelStage(row["stage"]),
            status=ModelStatus(row["status"]),
            run_id=row["run_id"],
            experiment_id=row["experiment_id"],
            source=row["source"],
            artifacts=[
                ModelArtifact(**a) for a in (row["artifacts"] or [])
            ],
            signature=ModelSignature(**row["signature"]) if row["signature"] else None,
            description=row["description"],
            tags=row["tags"] or {},
            params=row["params"] or {},
            metrics=row["metrics"] or {},
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            created_by=row["created_by"],
            parent_version=row["parent_version"],
            dataset_version=row["dataset_version"],
        )

    # ==================== Deployment Tracking ====================

    async def create_deployment(
        self,
        model_name: str,
        model_version: int,
        endpoint_name: str,
        endpoint_url: str,
        replicas: int = 1,
        resources: Dict[str, Any] = {},
        config: Dict[str, Any] = {},
        health_check_url: str = "",
    ) -> ModelDeployment:
        import uuid
        deployment_id = str(uuid.uuid4())

        async with self._pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO model_deployments (
                    id, model_name, model_version, endpoint_name, endpoint_url,
                    status, replicas, resources, config, health_check_url
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """, deployment_id, model_name, model_version, endpoint_name, endpoint_url,
                "deploying", replicas, json.dumps(resources), json.dumps(config), health_check_url)

        return ModelDeployment(
            id=deployment_id,
            model_name=model_name,
            model_version=model_version,
            endpoint_name=endpoint_name,
            endpoint_url=endpoint_url,
            status="deploying",
            replicas=replicas,
            resources=resources,
            config=config,
            health_check_url=health_check_url,
        )

    async def update_deployment_status(
        self,
        deployment_id: str,
        status: str,
        metrics: Dict[str, Any] = {},
    ):
        async with self._pool.acquire() as conn:
            await conn.execute("""
                UPDATE model_deployments 
                SET status = $1, metrics = $2, updated_at = NOW()
                WHERE id = $3
            """, status, json.dumps(metrics), deployment_id)

    async def get_deployment(self, deployment_id: str) -> Optional[ModelDeployment]:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM model_deployments WHERE id = $1", deployment_id)
            if not row:
                return None
            return ModelDeployment(
                id=row["id"],
                model_name=row["model_name"],
                model_version=row["model_version"],
                endpoint_name=row["endpoint_name"],
                endpoint_url=row["endpoint_url"],
                status=row["status"],
                replicas=row["replicas"],
                resources=row["resources"] or {},
                config=row["config"] or {},
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                health_check_url=row["health_check_url"],
                metrics=row["metrics"] or {},
            )

    async def list_deployments(self, model_name: Optional[str] = None) -> List[ModelDeployment]:
        async with self._pool.acquire() as conn:
            if model_name:
                rows = await conn.fetch("SELECT * FROM model_deployments WHERE model_name = $1", model_name)
            else:
                rows = await conn.fetch("SELECT * FROM model_deployments")

            return [
                ModelDeployment(
                    id=row["id"],
                    model_name=row["model_name"],
                    model_version=row["model_version"],
                    endpoint_name=row["endpoint_name"],
                    endpoint_url=row["endpoint_url"],
                    status=row["status"],
                    replicas=row["replicas"],
                    resources=row["resources"] or {},
                    config=row["config"] or {},
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                    health_check_url=row["health_check_url"],
                    metrics=row["metrics"] or {},
                )
                for row in rows
            ]


class ModelRegistry:
    """
    MLflow-compatible Model Registry.

    Features:
    - Model registration & versioning
    - Stage management (Staging/Production/Archived)
    - Artifact storage
    - Model signature validation
    - Deployment tracking
    - Lineage tracking
    """

    def __init__(
        self,
        artifact_store: Optional[ArtifactStore] = None,
        pg_dsn: str = "postgresql://postgres:postgres@localhost:5432/vcos",
    ):
        self.artifact_store = artifact_store or LocalArtifactStore()
        self.pg_registry = PostgresModelRegistry(pg_dsn)
        self._initialized = False

    async def initialize(self):
        await self.pg_registry.initialize()
        self._initialized = True
        logger.info("Model Registry initialized")

    async def close(self):
        await self.pg_registry.close()

    # ==================== Model Management ====================

    async def create_model(
        self,
        name: str,
        description: str = "",
        tags: Dict[str, str] = {},
    ) -> RegisteredModel:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.create_model(name, description, tags)

    async def get_model(self, name: str) -> Optional[RegisteredModel]:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.get_model(name)

    async def list_models(self, filter_tags: Dict[str, str] = {}) -> List[RegisteredModel]:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.list_models(filter_tags)

    async def delete_model(self, name: str):
        if not self._initialized:
            await self.initialize()
        await self.pg_registry.delete_model(name)

    # ==================== Version Management ====================

    async def register_model(
        self,
        name: str,
        run_id: str = "",
        experiment_id: str = "",
        source: str = "",
        version: Optional[int] = None,
        description: str = "",
        tags: Dict[str, str] = {},
        params: Dict[str, Any] = {},
        metrics: Dict[str, float] = {},
        signature: Optional[ModelSignature] = None,
        parent_version: Optional[int] = None,
        dataset_version: str = "",
        created_by: str = "",
    ) -> ModelVersion:
        if not self._initialized:
            await self.initialize()

        # Create model if not exists
        model = await self.get_model(name)
        if not model:
            await self.create_model(name)

        version_obj = await self.pg_registry.create_version(
            name=name,
            version=version,
            run_id=run_id,
            experiment_id=experiment_id,
            source=source,
            description=description,
            tags=tags,
            params=params,
            metrics=metrics,
            signature=signature,
            parent_version=parent_version,
            dataset_version="",
            created_by="",
        )
        return version_obj

    async def get_version(self, name: str, version: int) -> Optional[ModelVersion]:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.get_version(name, version)

    async def get_latest_version(self, name: str, stage: Optional[ModelStage] = None) -> Optional[ModelVersion]:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.get_latest_version(name, stage)

    async def list_versions(self, name: str) -> List[ModelVersion]:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.list_versions(name)

    async def transition_stage(self, name: str, version: int, stage: ModelStage):
        if not self._initialized:
            await self.initialize()
        await self.pg_registry.transition_stage(name, version, stage)

    async def add_artifacts(self, name: str, version: int, artifacts: List[ModelArtifact]):
        if not self._initialized:
            await self.initialize()

        # Save to artifact store
        saved_paths = await self.artifact_store.save(name, version, artifacts)

        # Update registry with paths
        for artifact, path in zip(artifacts, saved_paths):
            artifact.path = path

        await self.pg_registry.add_artifacts(name, version, artifacts)

    async def set_signature(self, name: str, version: int, signature: ModelSignature):
        if not self._initialized:
            await self.initialize()
        await self.pg_registry.set_signature(name, version, signature)

    async def transition_to_staging(self, name: str, version: int):
        await self.transition_stage(name, version, ModelStage.STAGING)

    async def transition_to_production(self, name: str, version: int):
        await self.transition_stage(name, version, ModelStage.PRODUCTION)

    async def archive(self, name: str, version: int):
        await self.transition_stage(name, version, ModelStage.ARCHIVED)

    # ==================== Deployment ====================

    async def create_deployment(
        self,
        model_name: str,
        model_version: int,
        endpoint_name: str,
        endpoint_url: str,
        replicas: int = 1,
        resources: Dict[str, Any] = {},
        config: Dict[str, Any] = {},
        health_check_url: str = "",
    ) -> ModelDeployment:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.create_deployment(
            model_name, model_version, endpoint_name, endpoint_url,
            replicas, {}, {}, "", ""
        )

    async def update_deployment_status(
        self,
        deployment_id: str,
        status: str,
        metrics: Dict[str, Any] = {},
    ):
        if not self._initialized:
            await self.initialize()
        await self.pg_registry.update_deployment_status(deployment_id, status, metrics)

    async def get_deployment(self, deployment_id: str) -> Optional[ModelDeployment]:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.get_deployment(deployment_id)

    async def list_deployments(self, model_name: Optional[str] = None) -> List[ModelDeployment]:
        if not self._initialized:
            await self.initialize()
        return await self.pg_registry.list_deployments(model_name)

    # ==================== Utilities ====================

    async def search_models(
        self,
        query: str = "",
        tags: Dict[str, str] = {},
        stage: Optional[ModelStage] = None,
    ) -> List[RegisteredModel]:
        models = await self.list_models({})
        results = []

        for model in models:
            if query and query.lower() not in model.name.lower():
                continue

            if tags:
                match = all(model.tags.get(k) == v for k, v in tags.items())
                if not match:
                    continue

            if stage:
                latest = await self.get_latest_version(model.name, stage)
                if not latest:
                    continue

            results.append(model)

        return results


# Global model registry instance
_model_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    """Get or create model registry singleton."""
    global _model_registry
    if _model_registry is None:
        pg_dsn = getattr(settings, 'DATABASE_URL', 'postgresql://postgres:postgres@localhost:5432/vcos')
        if pg_dsn.startswith("sqlite"):
            pg_dsn = "postgresql://postgres:postgres@localhost:5432/vcos"
        _model_registry = ModelRegistry(pg_dsn=pg_dsn)
    return _model_registry


def init_model_registry(
    artifact_store: Optional[ArtifactStore] = None,
    pg_dsn: str = "postgresql://postgres:postgres@localhost:5432/vcos",
) -> ModelRegistry:
    """Initialize model registry with custom config."""
    global _model_registry
    _model_registry = ModelRegistry(artifact_store=artifact_store, pg_dsn=pg_dsn)
    return _model_registry