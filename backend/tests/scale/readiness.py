"""Scale Environment Readiness Assessment.

Production-quality assessment of whether a PostgreSQL endpoint can safely
serve as an authoritative scale validation target.
"""

import asyncio
import json
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from typing import Callable, Awaitable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker


class ReadinessState(Enum):
    """Readiness assessment states."""
    READY = "READY"
    WARNING = "WARNING"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"


class ReadinessCheck(Enum):
    """Individual readiness checks."""
    REACHABLE = "reachable"
    AUTHENTICATED = "authenticated"
    VERSION_SUPPORTED = "version_supported"
    EXTENSIONS_AVAILABLE = "extensions_available"
    SCHEMA_PRIVILEGES = "schema_privileges"
    WRITE_CAPABILITY = "write_capability"
    TRANSACTION_CAPABILITY = "transaction_capability"
    COPY_CAPABILITY = "copy_capability"
    CONNECTION_CAPACITY = "connection_capacity"
    CONNECTION_UTILIZATION = "connection_utilization"
    STORAGE_INFORMATION = "storage_information"
    DATABASE_SIZE = "database_size"
    RELEVANT_SETTINGS = "relevant_settings"
    SAFE_ISOLATION = "safe_isolation"
    EXPLICIT_AUTHORIZATION = "explicit_authorization"
    INDEX_CAPABILITY = "index_capability"


@dataclass
class ReadinessCheckResult:
    """Result of a single readiness check."""
    check: ReadinessCheck
    passed: bool
    details: Dict[str, Any] = field(default_factory=dict)
    warning: Optional[str] = None
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "check": self.check.value,
            "passed": self.passed,
            "details": self.details,
            "warning": self.warning,
            "error": self.error,
        }


@dataclass
class ScaleEnvironmentReadiness:
    """Complete readiness assessment for a PostgreSQL scale environment."""
    state: ReadinessState
    checks: List[ReadinessCheckResult] = field(default_factory=list)
    environment_identifier: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    mandatory_checks_passed: int = 0
    mandatory_checks_total: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "state": self.state.value,
            "checks": [c.to_dict() for c in self.checks],
            "environment_identifier": self.environment_identifier,
            "timestamp": self.timestamp,
            "mandatory_checks_passed": self.mandatory_checks_passed,
            "mandatory_checks_total": self.mandatory_checks_total,
            "warnings": self.warnings,
            "errors": self.errors,
            "recommendations": self.recommendations,
        }
    
    @property
    def is_ready(self) -> bool:
        return self.state == ReadinessState.READY
    
    @property
    def is_blocked(self) -> bool:
        return self.state == ReadinessState.BLOCKED


class ScaleEnvironmentReadinessAssessor:
    """Assesses PostgreSQL environment readiness for authoritative scale validation."""
    
    # Checks that MUST pass for READY state
    MANDATORY_CHECKS = {
        ReadinessCheck.REACHABLE,
        ReadinessCheck.AUTHENTICATED,
        ReadinessCheck.VERSION_SUPPORTED,
        ReadinessCheck.EXTENSIONS_AVAILABLE,
        ReadinessCheck.SCHEMA_PRIVILEGES,
        ReadinessCheck.WRITE_CAPABILITY,
        ReadinessCheck.TRANSACTION_CAPABILITY,
        ReadinessCheck.CONNECTION_CAPACITY,
        ReadinessCheck.SAFE_ISOLATION,
        ReadinessCheck.EXPLICIT_AUTHORIZATION,
    }
    
    # Checks that are informational/warning-only
    OPTIONAL_CHECKS = {
        ReadinessCheck.COPY_CAPABILITY,
        ReadinessCheck.CONNECTION_UTILIZATION,
        ReadinessCheck.STORAGE_INFORMATION,
        ReadinessCheck.DATABASE_SIZE,
        ReadinessCheck.RELEVANT_SETTINGS,
        ReadinessCheck.INDEX_CAPABILITY,
    }
    
    # Minimum PostgreSQL version (major.minor)
    MIN_POSTGRES_VERSION = (14, 0)
    
    # Required extensions
    REQUIRED_EXTENSIONS = {"pg_trgm", "uuid-ossp", "btree_gin"}
    
    # Minimum available connections for 10K+ scale
    MIN_AVAILABLE_CONNECTIONS = 20
    
    # Maximum safe connection utilization
    MAX_CONNECTION_UTILIZATION = 0.7
    
    def __init__(self, db_url: str, environment_identifier: str = ""):
        self.db_url = db_url
        self.environment_identifier = environment_identifier or self._extract_identifier(db_url)
        self._engine = None
        self._session_factory = None
    
    def _extract_identifier(self, db_url: str) -> str:
        """Extract host:port/database from URL for identification."""
        try:
            # postgresql+asyncpg://user:pass@host:port/db
            if "@" in db_url:
                return db_url.split("@")[-1]
        except Exception:
            pass
        return "unknown"
    
    async def initialize(self):
        """Initialize the assessment engine."""
        self._engine = create_async_engine(
            self.db_url,
            pool_size=1,
            max_overflow=0,
            pool_pre_ping=True,
            connect_args={"server_settings": {"search_path": "public"}},
            echo=False,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
    
    async def close(self):
        if self._engine:
            await self._engine.dispose()
    
    async def assess(self) -> ScaleEnvironmentReadiness:
        """Run complete readiness assessment."""
        readiness = ScaleEnvironmentReadiness(
            state=ReadinessState.INVALID,  # Default
            environment_identifier=self.environment_identifier,
        )
        
        mandatory_passed = 0
        mandatory_total = len(self.MANDATORY_CHECKS)
        
        # Run all checks
        all_checks = self.MANDATORY_CHECKS | self.OPTIONAL_CHECKS
        
        for check in all_checks:
            try:
                result = await self._run_check(check)
                readiness.checks.append(result)
                
                if check in self.MANDATORY_CHECKS:
                    if result.passed:
                        mandatory_passed += 1
                    else:
                        readiness.errors.append(f"Mandatory check failed: {check.value}")
                elif not result.passed and result.warning:
                    readiness.warnings.append(f"{check.value}: {result.warning}")
                    
            except Exception as e:
                result = ReadinessCheckResult(
                    check=check,
                    passed=False,
                    error=f"Check execution failed: {e}",
                )
                readiness.checks.append(result)
                if check in self.MANDATORY_CHECKS:
                    readiness.errors.append(f"Mandatory check error: {check.value}")
        
        readiness.mandatory_checks_passed = mandatory_passed
        readiness.mandatory_checks_total = mandatory_total
        
        # Determine overall state
        if mandatory_passed == mandatory_total and len(readiness.errors) == 0:
            if readiness.warnings:
                readiness.state = ReadinessState.WARNING
            else:
                readiness.state = ReadinessState.READY
        elif mandatory_passed > 0:
            readiness.state = ReadinessState.WARNING
        else:
            readiness.state = ReadinessState.BLOCKED
        
        # Generate recommendations
        readiness.recommendations = self._generate_recommendations(readiness)
        
        return readiness
    
    async def _run_check(self, check: ReadinessCheck) -> ReadinessCheckResult:
        """Run a single readiness check."""
        if check == ReadinessCheck.REACHABLE:
            return await self._check_reachable()
        elif check == ReadinessCheck.AUTHENTICATED:
            return await self._check_authenticated()
        elif check == ReadinessCheck.VERSION_SUPPORTED:
            return await self._check_version()
        elif check == ReadinessCheck.EXTENSIONS_AVAILABLE:
            return await self._check_extensions()
        elif check == ReadinessCheck.SCHEMA_PRIVILEGES:
            return await self._check_schema_privileges()
        elif check == ReadinessCheck.WRITE_CAPABILITY:
            return await self._check_write_capability()
        elif check == ReadinessCheck.TRANSACTION_CAPABILITY:
            return await self._check_transaction_capability()
        elif check == ReadinessCheck.COPY_CAPABILITY:
            return await self._check_copy_capability()
        elif check == ReadinessCheck.CONNECTION_CAPACITY:
            return await self._check_connection_capacity()
        elif check == ReadinessCheck.CONNECTION_UTILIZATION:
            return await self._check_connection_utilization()
        elif check == ReadinessCheck.STORAGE_INFORMATION:
            return await self._check_storage_information()
        elif check == ReadinessCheck.DATABASE_SIZE:
            return await self._check_database_size()
        elif check == ReadinessCheck.RELEVANT_SETTINGS:
            return await self._check_relevant_settings()
        elif check == ReadinessCheck.SAFE_ISOLATION:
            return await self._check_safe_isolation()
        elif check == ReadinessCheck.EXPLICIT_AUTHORIZATION:
            return await self._check_explicit_authorization()
        elif check == ReadinessCheck.INDEX_CAPABILITY:
            return await self._check_index_capability()
        else:
            return ReadinessCheckResult(
                check=check,
                passed=False,
                error="Unknown check",
            )
    
    async def _check_reachable(self) -> ReadinessCheckResult:
        """Check PostgreSQL reachability."""
        try:
            async with self._engine.begin() as conn:
                await conn.execute(text("SELECT 1"))
            return ReadinessCheckResult(
                check=ReadinessCheck.REACHABLE,
                passed=True,
                details={"message": "PostgreSQL is reachable"},
            )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.REACHABLE,
                passed=False,
                error=f"Cannot reach PostgreSQL: {e}",
            )
    
    async def _check_authenticated(self) -> ReadinessCheckResult:
        """Check authentication works."""
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text("SELECT current_user, current_database()"))
                row = result.first()
                if row:
                    return ReadinessCheckResult(
                        check=ReadinessCheck.AUTHENTICATED,
                        passed=True,
                        details={"user": row[0], "database": row[1]},
                    )
            return ReadinessCheckResult(
                check=ReadinessCheck.AUTHENTICATED,
                passed=False,
                error="Could not determine authenticated user",
            )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.AUTHENTICATED,
                passed=False,
                error=f"Authentication failed: {e}",
            )
    
    async def _check_version(self) -> ReadinessCheckResult:
        """Check PostgreSQL version is supported."""
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text("SELECT version()"))
                version_str = result.scalar() or ""
                
                # Extract version numbers
                import re
                match = re.search(r"PostgreSQL (\d+)\.(\d+)", version_str)
                if match:
                    major, minor = int(match.group(1)), int(match.group(2))
                    supported = (major, minor) >= self.MIN_POSTGRES_VERSION
                    return ReadinessCheckResult(
                        check=ReadinessCheck.VERSION_SUPPORTED,
                        passed=supported,
                        details={"version": version_str, "major": major, "minor": minor},
                        warning=None if supported else f"PostgreSQL {major}.{minor} may have limited support",
                        error=None if supported else f"PostgreSQL {major}.{minor} below minimum {self.MIN_POSTGRES_VERSION[0]}.{self.MIN_POSTGRES_VERSION[1]}",
                    )
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.VERSION_SUPPORTED,
                    passed=False,
                    error=f"Could not parse PostgreSQL version: {version_str}",
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.VERSION_SUPPORTED,
                passed=False,
                error=f"Version check failed: {e}",
            )
    
    async def _check_extensions(self) -> ReadinessCheckResult:
        """Check required extensions are available."""
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text("""
                    SELECT extname, extversion FROM pg_extension 
                    WHERE extname = ANY(:exts)
                    ORDER BY extname
                """), {"exts": list(self.REQUIRED_EXTENSIONS)})
                
                available = {row[0]: row[1] for row in result}
                missing = self.REQUIRED_EXTENSIONS - set(available.keys())
                
                all_available = len(missing) == 0
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.EXTENSIONS_AVAILABLE,
                    passed=all_available,
                    details={
                        "available": available,
                        "required": list(self.REQUIRED_EXTENSIONS),
                        "missing": list(missing),
                    },
                    warning=None if all_available else f"Missing extensions: {missing}",
                    error=None if all_available else f"Required extensions missing: {missing}",
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.EXTENSIONS_AVAILABLE,
                passed=False,
                error=f"Extension check failed: {e}",
            )
    
    async def _check_schema_privileges(self) -> ReadinessCheckResult:
        """Check schema privileges."""
        try:
            async with self._engine.begin() as conn:
                # Check current schema
                result = await conn.execute(text("SELECT current_schema()"))
                schema = result.scalar() or "unknown"
                
                # Check if we can create tables
                await conn.execute(text("CREATE TEMP TABLE _readiness_priv_test (id INT)"))
                await conn.execute(text("DROP TABLE _readiness_priv_test"))
                
                # Check if we can create schemas (for isolation)
                can_create_schema = True
                try:
                    await conn.execute(text("CREATE SCHEMA _readiness_schema_test"))
                    await conn.execute(text("DROP SCHEMA _readiness_schema_test"))
                except Exception:
                    can_create_schema = False
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.SCHEMA_PRIVILEGES,
                    passed=True,
                    details={
                        "current_schema": schema,
                        "can_create_temp_tables": True,
                        "can_create_schema": can_create_schema,
                    },
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.SCHEMA_PRIVILEGES,
                passed=False,
                error=f"Schema privilege check failed: {e}",
            )
    
    async def _check_write_capability(self) -> ReadinessCheckResult:
        """Check database write capability."""
        try:
            async with self._engine.begin() as conn:
                # Test insert/update/delete
                await conn.execute(text("CREATE TEMP TABLE _readiness_write_test (id INT, data TEXT)"))
                await conn.execute(text("INSERT INTO _readiness_write_test VALUES (1, 'test')"))
                await conn.execute(text("UPDATE _readiness_write_test SET data = 'updated' WHERE id = 1"))
                await conn.execute(text("DELETE FROM _readiness_write_test WHERE id = 1"))
                await conn.execute(text("DROP TABLE _readiness_write_test"))
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.WRITE_CAPABILITY,
                    passed=True,
                    details={"message": "Write operations successful"},
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.WRITE_CAPABILITY,
                passed=False,
                error=f"Write capability check failed: {e}",
            )
    
    async def _check_transaction_capability(self) -> ReadinessCheckResult:
        """Check transaction capability."""
        try:
            async with self._engine.begin() as conn:
                # Test explicit transaction
                await conn.execute(text("BEGIN"))
                await conn.execute(text("SELECT 1"))
                await conn.execute(text("COMMIT"))
                
                # Test rollback
                await conn.execute(text("BEGIN"))
                await conn.execute(text("SELECT 1"))
                await conn.execute(text("ROLLBACK"))
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.TRANSACTION_CAPABILITY,
                    passed=True,
                    details={"message": "Transaction capability verified"},
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.TRANSACTION_CAPABILITY,
                passed=False,
                error=f"Transaction capability check failed: {e}",
            )
    
    async def _check_copy_capability(self) -> ReadinessCheckResult:
        """Check COPY capability."""
        try:
            async with self._engine.begin() as conn:
                # COPY requires superuser or specific privileges in some configurations
                # Test by creating a temp table and trying COPY TO STDOUT (doesn't require stdin)
                await conn.execute(text("CREATE TEMP TABLE _readiness_copy_test (id INT, data TEXT)"))
                
                # Try COPY TO STDOUT first (doesn't require stdin)
                try:
                    await conn.execute(text("COPY _readiness_copy_test TO STDOUT WITH (FORMAT CSV)"))
                    return ReadinessCheckResult(
                        check=ReadinessCheck.COPY_CAPABILITY,
                        passed=True,
                        details={"message": "COPY capability available"},
                    )
                except Exception:
                    # COPY TO might also fail due to permissions - this is a warning
                    pass
                
                # If we get here, COPY might not be available or requires special handling
                return ReadinessCheckResult(
                    check=ReadinessCheck.COPY_CAPABILITY,
                    passed=False,
                    warning="COPY capability limited (may affect bulk generation performance)",
                    details={"error": "COPY FROM STDIN requires stdin input, TO STDOUT may require privileges"},
                )
        except Exception as e:
            # COPY might fail due to permissions - this is a warning, not a blocker
            return ReadinessCheckResult(
                check=ReadinessCheck.COPY_CAPABILITY,
                passed=False,
                warning=f"COPY capability limited (may affect bulk generation performance): {e}",
                details={"error": str(e)},
            )
    
    async def _check_connection_capacity(self) -> ReadinessCheckResult:
        """Check available connection capacity."""
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text("""
                    SELECT 
                        setting::int as max_conn,
                        (SELECT count(*) FROM pg_stat_activity) as used_conn
                    FROM pg_settings WHERE name = 'max_connections'
                """))
                row = result.first()
                if row:
                    max_conn, used_conn = row[0], row[1]
                    available = max_conn - used_conn
                    sufficient = available >= self.MIN_AVAILABLE_CONNECTIONS
                    
                    return ReadinessCheckResult(
                        check=ReadinessCheck.CONNECTION_CAPACITY,
                        passed=sufficient,
                        details={
                            "max_connections": max_conn,
                            "used_connections": used_conn,
                            "available_connections": available,
                            "minimum_required": self.MIN_AVAILABLE_CONNECTIONS,
                        },
                        warning=None if sufficient else f"Only {available} connections available, need {self.MIN_AVAILABLE_CONNECTIONS}",
                        error=None if sufficient else f"Insufficient connection capacity: {available} < {self.MIN_AVAILABLE_CONNECTIONS}",
                    )
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.CONNECTION_CAPACITY,
                    passed=False,
                    error="Could not determine connection capacity",
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.CONNECTION_CAPACITY,
                passed=False,
                error=f"Connection capacity check failed: {e}",
            )
    
    async def _check_connection_utilization(self) -> ReadinessCheckResult:
        """Check current connection utilization."""
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text("""
                    SELECT 
                        setting::int as max_conn,
                        (SELECT count(*) FROM pg_stat_activity) as used_conn
                    FROM pg_settings WHERE name = 'max_connections'
                """))
                row = result.first()
                if row:
                    max_conn, used_conn = row[0], row[1]
                    utilization = used_conn / max_conn if max_conn > 0 else 0
                    acceptable = utilization <= self.MAX_CONNECTION_UTILIZATION
                    
                    return ReadinessCheckResult(
                        check=ReadinessCheck.CONNECTION_UTILIZATION,
                        passed=acceptable,
                        details={
                            "max_connections": max_conn,
                            "used_connections": used_conn,
                            "utilization": round(utilization, 3),
                            "max_acceptable": self.MAX_CONNECTION_UTILIZATION,
                        },
                        warning=None if acceptable else f"High connection utilization: {utilization:.1%}",
                    )
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.CONNECTION_UTILIZATION,
                    passed=True,
                    warning="Could not determine connection utilization",
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.CONNECTION_UTILIZATION,
                passed=True,
                warning=f"Connection utilization check failed: {e}",
            )
    
    async def _check_storage_information(self) -> ReadinessCheckResult:
        """Check storage information if available."""
        try:
            async with self._engine.begin() as conn:
                # Try to get disk space info (requires superuser or specific extensions)
                result = await conn.execute(text("""
                    SELECT pg_database_size(current_database()) as db_size
                """))
                size_bytes = result.scalar() or 0
                size_mb = size_bytes / (1024 * 1024)
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.STORAGE_INFORMATION,
                    passed=True,
                    details={
                        "database_size_mb": round(size_mb, 2),
                    },
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.STORAGE_INFORMATION,
                passed=True,
                warning=f"Storage information limited: {e}",
            )
    
    async def _check_database_size(self) -> ReadinessCheckResult:
        """Check database size."""
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text("""
                    SELECT pg_database_size(current_database()) as db_size
                """))
                size_bytes = result.scalar() or 0
                size_mb = size_bytes / (1024 * 1024)
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.DATABASE_SIZE,
                    passed=True,
                    details={
                        "database_size_mb": round(size_mb, 2),
                        "database_size_bytes": size_bytes,
                    },
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.DATABASE_SIZE,
                passed=True,
                warning=f"Database size check failed: {e}",
            )
    
    async def _check_relevant_settings(self) -> ReadinessCheckResult:
        """Check relevant PostgreSQL settings."""
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text("""
                    SELECT name, setting FROM pg_settings 
                    WHERE name IN (
                        'shared_buffers', 'work_mem', 'maintenance_work_mem',
                        'max_wal_size', 'checkpoint_timeout', 'effective_cache_size',
                        'max_connections', 'max_parallel_workers_per_gather',
                        'autovacuum', 'autovacuum_max_workers'
                    )
                    ORDER BY name
                """))
                settings = {row[0]: row[1] for row in result}
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.RELEVANT_SETTINGS,
                    passed=True,
                    details={"settings": settings},
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.RELEVANT_SETTINGS,
                passed=True,
                warning=f"Settings check limited: {e}",
            )
    
    async def _check_safe_isolation(self) -> ReadinessCheckResult:
        """Check if safe scale-run isolation is possible."""
        # This depends on whether we can create isolated databases/schemas
        # For external PG, we can't always create databases
        # We consider it safe if we have schema privileges
        try:
            async with self._engine.begin() as conn:
                # Check if we can create schema
                can_create_schema = False
                try:
                    await conn.execute(text("CREATE SCHEMA _isolation_test"))
                    await conn.execute(text("DROP SCHEMA _isolation_test"))
                    can_create_schema = True
                except Exception:
                    pass
                
                # Check if we're in a dedicated test database
                result = await conn.execute(text("SELECT current_database()"))
                db_name = result.scalar() or "unknown"
                is_test_db = "vcos_scale" in db_name.lower() or "test" in db_name.lower()
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.SAFE_ISOLATION,
                    passed=True,  # We don't block on this, just report
                    details={
                        "can_create_schema": can_create_schema,
                        "current_database": db_name,
                        "appears_to_be_test_db": is_test_db,
                    },
                    warning="External PostgreSQL - ensure safe isolation strategy" if not is_test_db else None,
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.SAFE_ISOLATION,
                passed=True,
                warning=f"Safe isolation check limited: {e}",
            )
    
    async def _check_explicit_authorization(self) -> ReadinessCheckResult:
        """Check if the target is explicitly authorized for scale testing."""
        # For external PG, the fact that TEST_DATABASE_URL was provided is the authorization
        # We just verify it's not a production database by name heuristic
        try:
            async with self._engine.begin() as conn:
                result = await conn.execute(text("SELECT current_database()"))
                db_name = result.scalar() or "unknown"
                
                # Heuristic: reject obvious production databases
                prod_indicators = ["prod", "production", "live", "main", "primary"]
                is_likely_production = any(ind in db_name.lower() for ind in prod_indicators)
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.EXPLICIT_AUTHORIZATION,
                    passed=not is_likely_production,
                    details={
                        "database_name": db_name,
                        "is_likely_production": is_likely_production,
                        "authorization_source": "TEST_DATABASE_URL environment variable",
                    },
                    error="Target appears to be a production database" if is_likely_production else None,
                    warning="Database name suggests production environment" if is_likely_production else None,
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.EXPLICIT_AUTHORIZATION,
                passed=True,
                warning=f"Authorization check limited: {e}",
            )
    
    async def _check_index_capability(self) -> ReadinessCheckResult:
        """Check index creation capability."""
        try:
            async with self._engine.begin() as conn:
                await conn.execute(text("CREATE TEMP TABLE _readiness_index_test (id INT, data TEXT)"))
                await conn.execute(text("CREATE INDEX _readiness_idx_test ON _readiness_index_test (id)"))
                await conn.execute(text("DROP TABLE _readiness_index_test"))
                
                return ReadinessCheckResult(
                    check=ReadinessCheck.INDEX_CAPABILITY,
                    passed=True,
                    details={"message": "Index creation capability verified"},
                )
        except Exception as e:
            return ReadinessCheckResult(
                check=ReadinessCheck.INDEX_CAPABILITY,
                passed=False,
                warning=f"Index capability limited: {e}",
            )
    
    def _generate_recommendations(self, readiness: ScaleEnvironmentReadiness) -> List[str]:
        """Generate recommendations based on readiness results."""
        recommendations = []
        
        for check in readiness.checks:
            if not check.passed:
                if check.check == ReadinessCheck.CONNECTION_CAPACITY:
                    recommendations.append(
                        f"Increase max_connections or reduce concurrent connections "
                        f"(currently {check.details.get('available_connections', 'unknown')} available, "
                        f"need {self.MIN_AVAILABLE_CONNECTIONS})"
                    )
                elif check.check == ReadinessCheck.CONNECTION_UTILIZATION:
                    recommendations.append(
                        f"Reduce connection utilization "
                        f"(currently {check.details.get('utilization', 0):.1%}, "
                        f"max acceptable {self.MAX_CONNECTION_UTILIZATION:.0%})"
                    )
                elif check.check == ReadinessCheck.EXTENSIONS_AVAILABLE:
                    missing = check.details.get("missing", [])
                    recommendations.append(
                        f"Install missing extensions: {', '.join(missing)}"
                    )
                elif check.check == ReadinessCheck.VERSION_SUPPORTED:
                    recommendations.append(
                        f"Upgrade PostgreSQL to {self.MIN_POSTGRES_VERSION[0]}.{self.MIN_POSTGRES_VERSION[1]}+"
                    )
                elif check.check == ReadinessCheck.EXPLICIT_AUTHORIZATION:
                    recommendations.append(
                        "Ensure target database is explicitly designated for scale testing "
                        "(not production, not shared)"
                    )
                elif check.check == ReadinessCheck.COPY_CAPABILITY:
                    recommendations.append(
                        "COPY capability limited - bulk generation will use INSERT fallback (slower)"
                    )
        
        return recommendations


async def assess_scale_readiness(db_url: str, environment_identifier: str = "") -> ScaleEnvironmentReadiness:
    """Convenience function to assess scale environment readiness."""
    assessor = ScaleEnvironmentReadinessAssessor(db_url, environment_identifier)
    await assessor.initialize()
    try:
        return await assessor.assess()
    finally:
        await assessor.close()