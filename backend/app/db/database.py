import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

from sqlalchemy import MetaData, text, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import DateTime, String

from app.core.config import get_settings

# Convention for naming constraints
convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
metadata = MetaData(naming_convention=convention)


def gen_uuid() -> str:
    """Generate a UUID string."""
    return str(uuid.uuid4())


class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=False
    )


class Base(DeclarativeBase):
    metadata = metadata

    def dict(self) -> dict[str, Any]:
        return {c.name: getattr(self, c.name) for c in self.__table__.columns}

    def utcnow(self) -> datetime:
        return datetime.now(timezone.utc)


_engine = None
_async_session_maker = None


def _create_engine():
    """Create engine after ensuring database file is deleted for SQLite in DEBUG mode."""
    global _engine, _async_session_maker
    
    settings = get_settings()
    
    # Delete SQLite database file FIRST - before engine creation (for SQLite in DEBUG mode)
    if settings.DEBUG and settings.DATABASE_URL.startswith("sqlite"):
        import os
        db_path = settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if os.path.exists(db_path):
            os.remove(db_path)
            print(f"Deleted existing database file: {db_path}")
    
    url = settings.DATABASE_URL
    kwargs: dict[str, Any] = {"echo": settings.DB_ECHO, "pool_pre_ping": True}
    if url.startswith("postgresql"):
        kwargs.update(
            pool_size=settings.DB_POOL_SIZE,
            max_overflow=settings.DB_MAX_OVERFLOW,
            connect_args={"server_settings": {"search_path": "public"}},
        )
        eng = create_async_engine(url, **kwargs)

        # Register event listener to set search_path on every new async connection (PostgreSQL only)
        @event.listens_for(eng.sync_engine, "connect")
        def set_search_path(dbapi_connection, connection_record):
            if hasattr(dbapi_connection, "execute"):
                dbapi_connection.execute("SET search_path TO public")
    elif url.startswith("sqlite"):
        # SQLite-specific configuration for Windows to prevent locking issues
        connect_args = {
            "check_same_thread": False,
            "timeout": 30,
        }
        eng = create_async_engine(
            url, 
            **kwargs,
            connect_args=connect_args,
            poolclass=None,  # No pooling for SQLite
        )
        
        # Enable WAL mode and other SQLite optimizations for Windows
        @event.listens_for(eng.sync_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            # Enable WAL mode for better concurrency
            cursor.execute("PRAGMA journal_mode=WAL;")
            # Enable foreign keys
            cursor.execute("PRAGMA foreign_keys=ON;")
            # Increase cache size
            cursor.execute("PRAGMA cache_size=-32768;")  # 32MB
            # Synchronous mode NORMAL is faster than FULL
            cursor.execute("PRAGMA synchronous=NORMAL;")
            # Busy timeout
            cursor.execute("PRAGMA busy_timeout=30000;")  # 30 seconds
            # Temp store in memory
            cursor.execute("PRAGMA temp_store=MEMORY;")
            cursor.close()
    else:
        eng = create_async_engine(url, **kwargs)

    _engine = eng
    _async_session_maker = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    return eng


def get_engine():
    """Get or create the engine."""
    global _engine
    if _engine is None:
        return _create_engine()
    return _engine


def get_async_session_maker():
    """Get or create the async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        _create_engine()
    return _async_session_maker


# Initialize engine on first access
engine = get_engine()
async_session_maker = get_async_session_maker()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with get_async_session_maker()() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    # Import all models to register them with SQLAlchemy metadata
    from app.models import (  # noqa: F401
        organization,
        user,
        role,
        notification,
        workspace,
        ai,
        invitation,
        employee,
        department,
        team,
        skill,
        project,
        task,
        goal,
        meeting,
        calendar,
        collaboration,
        approval,
        governance,
        workload,
        knowledge,
        communication,
        executive,
        autonomy,
        continuous_twin,
        canonical_reliability,
        observability,
        workflow,
        enterprise,
        feature_flags,
        infrastructure,
        deployment_completeness,
        backup_manifest,
        release,
        industry,
        industry_module,
        industry_template,
        industry_policy,
        industry_configuration,
        digital_twin,
        developer,
        company_state,
        autonomous_plan,
        briefing,
        company_memory,
        decision_history,
        innovation,
        learning_cycle,
        optimization,
        organization_edge,
        organization_health,
        organization_node,
        prediction,
        recommendation,
        simulation,
        strategy_report,
        executive_intelligence,
        ai_governance,
        resilience_plan,
        brain,
        company_actions,
        organizational_learning,
        people_intelligence,
        skills_intelligence,
        ownership_intelligence,
        collaboration_intelligence,
        org_capability_intelligence,
        people_decision,
        execution_intelligence,
        execution_coordination,
        execution_strategy,
        resource_allocation_intelligence,
        customer_intelligence,
        business_commercial,
        business_performance,
        financial_resource_procurement,
        canonical_resource_asset,
        canonical_procurement_vendor,
        canonical_economic_intelligence,
        canonical_business_process,
        canonical_knowledge,
        canonical_communication_collaboration,
        canonical_business_intelligence,
        canonical_workforce,
        canonical_integration,
        company_operating,
        company_intent,
        canonical_company_continuity,
        longitudinal,
        learning_profile,
        course,
        learning_path,
        skill_gap,
        certification,
        assessment,
        academy,
        mentorship,
        career,
        onboarding,
        learning_recommendation,
        hr,
        customer,
        lead,
        contract,
        ticket,
        partner,
        portal,
        finance,
        adaptive_operating_profile,
        company_experience,
        company_actions,
        company_intent,
        canonical_company_continuity,
        longitudinal,
        learning_profile,
        course,
        learning_path,
        skill_gap,
        certification,
        assessment,
        academy,
        mentorship,
        career,
        onboarding,
        learning_recommendation,
        hr,
        customer,
        lead,
        contract,
        ticket,
        partner,
        portal,
        finance,
    )

    from app.db.database import get_engine, Base

    engine = get_engine()
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Tables in metadata before create_all: {list(Base.metadata.tables.keys())}")

    settings = get_settings()
    
    # For SQLite, use async connection with autocommit to handle index conflicts
    if settings.DATABASE_URL.startswith("sqlite"):
        # Use connection with AUTOCOMMIT to avoid rollback on index conflicts
        async with engine.connect() as conn:
            await conn.execution_options(isolation_level="AUTOCOMMIT")
            # Create pgvector extension for vector search (PostgreSQL only)
            if settings.DATABASE_URL.startswith("postgresql"):
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            try:
                # Use run_sync with a function that handles index conflicts
                def create_all_with_retry(sync_conn):
                    # Create all tables, catching index errors
                    for table_name, table in Base.metadata.tables.items():
                        try:
                            table.create(sync_conn, checkfirst=True)
                        except Exception as e:
                            error_msg = str(e).lower()
                            if "already exists" in error_msg or "duplicate" in error_msg:
                                logger.warning(f"Skipping existing table/index {table_name}: {e}")
                            else:
                                raise
                
                await conn.run_sync(create_all_with_retry)
                logger.info("Database tables created successfully")
            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "duplicate" in error_msg:
                    logger.warning(f"Database schema creation had issues (likely duplicate tables/indexes): {e}")
                else:
                    logger.error(f"Database schema creation failed: {e}")
                    raise
    else:
        # For PostgreSQL, use normal transaction
        async with engine.begin() as conn:
            if settings.DATABASE_URL.startswith("postgresql"):
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            try:
                await conn.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, checkfirst=True))
                logger.info("Database tables created successfully")
            except Exception as e:
                error_msg = str(e).lower()
                if "already exists" in error_msg or "duplicate" in error_msg:
                    logger.warning(f"Database schema creation had issues (likely duplicate tables/indexes): {e}")
                else:
                    logger.error(f"Database schema creation failed: {e}")
                    raise


async def close_db():
    engine = get_engine()
    await engine.dispose()