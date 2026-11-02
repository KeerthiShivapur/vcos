#!/usr/bin/env python3
"""
Gate 35-D - Query Plan Engineering Benchmark Script

This script runs EXPLAIN (ANALYZE, BUFFERS) on the key production queries
from Gates 35-A (Company Context), 35-B (Full-Text Search), and 35-C (Cursor Pagination)
to identify bottlenecks and optimize query plans.
"""

import asyncio
import os
import json
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy import select, func, text, or_, and_
from sqlalchemy.orm import selectinload

from app.db.database import Base, init_db
from app import models
from app.models.project import Project
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.task import Task
from app.models.meeting import Meeting
from app.models.document import Document
from app.models.knowledge import Document as KnowledgeDocument, WikiPage, Policy, SOP, Template
from app.models.communication import Conversation, ConversationMember, Message
from app.models.knowledge import Decision
from app.models.observability import CanonicalObservation
from app.models.continuous_twin import CompanyAttention
from app.models.canonical_reliability import CanonicalOperation
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization, CompanyObjective, CompanyGoal
from app.models.canonical_integration import ConnectorInstance, SyncRun
from app.models.enterprise import SecurityEvent

from app.intelligence.company_context import build_context, resolve_caller_access
from app.services.postgres_fulltext_search import PostgresFullTextSearchService, SearchMode
from app.services.search_service import search_service
from app.services.observability_service import observability_service
from app.intelligence.company_context_optimized_v2 import build_context_optimized
from app.utils.pagination import CursorPaginator, Cursor, paginate_projects, paginate_tasks, paginate_observations
from app.services.canonical_company_continuity_service import canonical_company_continuity_service
from app.services.canonical_reliability_service import canonical_reliability_service
from app.services.observability_service import observability_service

from app.db.database import Base
from app import models
from app.core.config import get_settings
from app.core.timeutils import utcnow

import uuid
import time

# Get settings
settings = get_settings()

# Use real PostgreSQL for benchmarking
PG_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/vcos_test")


@dataclass
class BenchmarkResult:
    query_name: str
    query_type: str
    planning_time_ms: float
    execution_time_ms: float
    rows_returned: int
    rows_removed_by_filter: int
    plan_nodes: List[Dict]
    total_cost: float
    actual_rows: int
    shared_hit_blocks: int
    shared_read_blocks: int
    temp_written_blocks: int
    temp_read_blocks: int
    plan_json: Dict
    sql: str


class QueryPlanBenchmark:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.results: List[BenchmarkResult] = []
    
    async def run_explain_analyze(self, query: str, params: Dict = None, name: str = "") -> BenchmarkResult:
        """Run EXPLAIN (ANALYZE, BUFFERS) on a query and capture results."""
        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}"
        start = time.perf_counter()
        
        try:
            result = await self.db.execute(text(query))
            elapsed = time.perf_counter() - start
            
            # Parse the JSON output
            plan = result.scalar()
            if isinstance(plan, list):
                plan = plan[0]
            
            # Extract key metrics
            plan_data = plan.get('Plan', {})
            
            result = BenchmarkResult(
                query_name=name,
                query_type=self._classify_query(query),
                planning_time_ms=plan.get('Planning Time', 0),
                execution_time_ms=plan.get('Execution Time', 0),
                rows_returned=plan_data.get('Actual Rows', 0),
                rows_removed_by_filter=plan_data.get('Rows Removed by Filter', 0),
                plan_nodes=[plan_data],
                total_cost=plan_data.get('Total Cost', 0),
                actual_rows=plan_data.get('Actual Rows', 0),
                shared_hit_blocks=plan_data.get('Shared Hit Blocks', 0),
                shared_read_blocks=plan_data.get('Shared Read Blocks', 0),
                temp_written_blocks=plan_data.get('Temp Written Blocks', 0),
                temp_read_blocks=plan_data.get('Temp Read Blocks', 0),
                plan_json=plan,
                sql=query
            )
            
            self.results.append(result)
            return result
            
        except Exception as e:
            print(f"Error running EXPLAIN ANALYZE on {name}: {e}")
            return BenchmarkResult(
                query_name=name,
                query_type="ERROR",
                planning_time_ms=0,
                execution_time_ms=0,
                rows_returned=0,
                rows_removed_by_filter=0,
                plan_nodes=[],
                total_cost=0,
                actual_rows=0,
                shared_hit_blocks=0,
                shared_read_blocks=0,
                temp_written_blocks=0,
                temp_read_blocks=0,
                plan_json={},
                sql=query
            )
    
    def _classify_query(self, query: str) -> str:
        """Classify the query type based on SQL."""
        query_lower = query.lower()
        if 'websearch_to_tsquery' in query_lower or 'to_tsvector' in query_lower or 'ts_rank' in query_lower:
            return "FTS"
        elif 'websearch_to_tsquery' in query_lower and 'similarity' in query_lower:
            return "HYBRID"
        elif 'similarity' in query_lower or 'trigram' in query_lower:
            return "TRIGRAM"
        elif 'offset' in query.lower() and 'limit' in query.lower() and 'cursor' not in query.lower():
            return "OFFSET_PAGINATION"
        elif 'cursor' in query.lower() or 'updated_at' in query.lower() and 'id' in query:
            return "CURSOR_PAGINATION"
        elif 'company_brain' in query.lower() or 'company_context' in query.lower() or 'build_context' in query.lower():
            return "COMPANY_CONTEXT"
        elif 'websearch_to_tsquery' in query_lower or 'ts_rank' in query_lower or 'similarity' in query_lower:
            return "SEARCH"
        elif 'select' in query_lower and 'from' in query_lower:
            return "SELECT"
        return "OTHER"
    
    def print_summary(self):
        """Print a summary of all benchmark results."""
        print("\n" + "="*80)
        print("QUERY PLAN BENCHMARK SUMMARY")
        print("="*80)
        
        by_type = {}
        for r in self.results:
            if r.query_type not in by_type:
                by_type[r.query_type] = []
            by_type[r.query_type].append(r)
        
        for qtype, results in by_type.items():
            print(f"\n{qtype} ({len(results)} queries):")
            for r in results:
                print(f"  {r.query_name}:")
                print(f"    Planning: {r.planning_time_ms:.2f}ms, Execution: {r.execution_time_ms:.2f}ms")
                print(f"    Rows: {r.rows_returned} returned, {r.rows_removed_by_filter} removed by filter")
                print(f"    Cost: {r.total_cost:.2f}, Shared Hit: {r.shared_hit_blocks}, Read: {r.shared_read_blocks}")
                if r.plan_json:
                    plan = r.plan_json.get('Plan', {})
                    print(f"    Plan: {plan.get('Node Type', 'Unknown')} - {plan.get('Actual Rows', 0)} rows")
        
        # Summary stats
        total_exec = sum(r.execution_time_ms for r in self.results)
        total_plan = sum(r.planning_time_ms for r in self.results)
        print(f"\nTotal Planning Time: {total_plan:.2f}ms")
        print(f"Total Execution Time: {total_exec:.2f}ms")
        print(f"Total Queries: {len(self.results)}")
        
        # Save results
        self.save_results()
    
    def save_results(self):
        """Save benchmark results to JSON file."""
        output = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "results": [
                {
                    "query_name": r.query_name,
                    "query_type": r.query_type,
                    "planning_time_ms": r.planning_time_ms,
                    "execution_time_ms": r.execution_time_ms,
                    "rows_returned": r.rows_returned,
                    "rows_removed_by_filter": r.rows_removed_by_filter,
                    "total_cost": r.total_cost,
                    "actual_rows": r.actual_rows,
                    "shared_hit_blocks": r.shared_hit_blocks,
                    "shared_read_blocks": r.shared_read_blocks,
                    "temp_written_blocks": r.temp_written_blocks,
                    "temp_read_blocks": r.temp_read_blocks,
                    "sql": r.sql,
                }
                for r in self.results
            ]
        }
        
        os.makedirs("benchmarks", exist_ok=True)
        filename = f"benchmarks/gate35d_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(output, f, indent=2, default=str)
        print(f"\nResults saved to {filename}")


async def setup_test_data(db: AsyncSession, org_id: str, scale: str = "small") -> Dict[str, int]:
    """Create test data at various scales for benchmarking."""
    
    scale_sizes = {
        "small": {"employees": 50, "projects": 20, "tasks": 100, "documents": 30, "knowledge": 50},
        "medium": {"employees": 500, "projects": 200, "tasks": 1000, "documents": 300, "knowledge": 500},
        "large": {"employees": 5000, "projects": 2000, "tasks": 10000, "documents": 3000, "knowledge": 5000},
    }
    
    sizes = scale_sizes.get(scale, scale_sizes["small"])
    
    print(f"Creating test data at {scale} scale: {sizes}")
    
    # Create organization
    org = Organization(
        id="bench-org",
        name="Benchmark Org",
        slug="benchmark-org",
        industry="Technology",
        country="US",
        timezone="UTC",
        currency="USD",
    )
    db.add(org)
    await db.flush()
    
    # Create users and employees
    for i in range(sizes["employees"]):
        user = User(
            id=f"user-{i:06d}",
            organization_id="bench-org",
            email=f"user{i}@benchmark.com",
            full_name=f"User {i}",
            password_hash="hash",
            status="active",
        )
        db.add(user)
        await db.flush()
        
        emp = Employee(
            id=f"emp-{i:06d}",
            organization_id="bench-org",
            user_id=f"user-{i:06d}",
            employee_number=f"E{i:06d}",
            first_name=f"User{i}",
            last_name=f"User{i}",
            email=f"user{i}@benchmark.com",
            designation=f"Role {i % 10}",
            status="active",
            joining_date=datetime.now(timezone.utc) - timedelta(days=i % 365),
        )
        db.add(emp)
    
    await db.flush()
    
    # Create projects
    for i in range(sizes["projects"]):
        p = Project(
            id=f"proj-{i:06d}",
            organization_id="bench-org",
            name=f"Project {i}",
            code=f"PRJ{i:04d}",
            description=f"Project {i} description",
            status="active" if i % 5 != 0 else "completed",
            progress=i * 7 % 100,
            start_date=datetime.now(timezone.utc) - timedelta(days=i*30),
            due_date=datetime.now(timezone.utc) + timedelta(days=365 - i*30),
        )
        db.add(p)
    
    await db.flush()
    
    # Create tasks
    project_ids = [f"proj-{i:06d}" for i in range(sizes["projects"])]
    for i in range(sizes["tasks"]):
        t = Task(
            id=f"task-{i:06d}",
            organization_id="bench-org",
            project_id=project_ids[i % len(project_ids)],
            title=f"Task {i}",
            description=f"Task {i} description",
            status=["pending", "in_progress", "completed", "blocked"][i % 4],
            priority=["low", "medium", "high", "critical"][i % 4],
            assignee_id=f"emp-{(i*7) % sizes['employees']:06d}",
            reporter_id=f"emp-{(i*11) % sizes['employees']:06d}",
            start_date=datetime.now(timezone.utc) - timedelta(days=i*7),
            due_date=datetime.now(timezone.utc) + timedelta(days=30 - i*7),
            progress=i * 10 % 100,
        )
        db.add(t)
    
    await db.flush()
    
    # Create documents
    for i in range(sizes["documents"]):
        d = Document(
            id=f"doc-{i:06d}",
            organization_id="bench-org",
            title=f"Document {i}",
            slug=f"doc-{i:06d}",
            description=f"Document {i} description",
            category=["architecture", "process", "guide", "reference", "spec", "runbook"][i % 6],
            status=["draft", "published", "archived"][i % 3],
            author_id=f"emp-{(i*7) % sizes['employees']:06d}",
            owner_id=f"emp-{(i*11) % sizes['employees']:06d}",
            project_id=f"proj-{(i*13) % sizes['projects']:06d}",
            status="published",
            content=f"Content for document {i}",
            version="1.0",
        )
        db.add(d)
    
    await db.flush()
    
    # Create knowledge items
    for i in range(sizes["knowledge"]):
        ki = KnowledgeIndex(
            id=f"ki-{i:06d}",
            organization_id="bench-org",
            entity_type=["document", "wiki", "policy", "sop", "template"][i % 5],
            entity_id=f"doc-{(i*7) % sizes['documents']:06d}",
            title=f"Knowledge {i}",
            content=f"Knowledge content {i} about important topics",
            keywords_json=f'["tag{i%10}", "category{i%5}", "topic{i%3}"]',
            status="published",
        )
        db.add(ki)
    
    await db.commit()
    
    return sizes


async def run_company_context_benchmarks(db: AsyncSession, org_id: str, user_id: str) -> List[BenchmarkResult]:
    """Run EXPLAIN ANALYZE on Company Context / Company Brain queries."""
    
    benchmark = QueryPlanBenchmark(db)
    results = []
    
    # Test user
    user = await db.get(User, "user-000000")
    
    print("\n=== COMPANY CONTEXT / COMPANY BRAIN QUERIES ===")
    
    # 1. Company Context build_context (the main Company Brain entry point)
    query = """
    SELECT p.id, p.name, p.code, p.description, p.status, p.progress, p.updated_at
    FROM projects p
    WHERE p.organization_id = 'bench-org'
    AND p.status IN ('active', 'planning')
    ORDER BY p.updated_at DESC
    LIMIT 20
    """
    result = await run_explain_analyze(db, "Company Context - Projects", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 2. Employee context query
    query = """
    SELECT e.id, e.first_name, e.last_name, e.email, e.designation, e.status, e.department_id, e.team_id
    FROM employees e
    WHERE e.organization_id = 'bench-org'
    AND e.status = 'active'
    ORDER BY e.updated_at DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "Company Context - Employees", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 3. Tasks with project context
    query = """
    SELECT t.id, t.title, t.description, t.status, t.priority, t.assignee_id, t.project_id, t.progress
    FROM tasks t
    WHERE t.organization_id = 'bench-org'
    AND t.status IN ('pending', 'in_progress', 'blocked')
    ORDER BY t.updated_at DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "Company Context - Tasks", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 4. Decisions with project context
    query = """
    SELECT d.id, d.title, d.description, d.status, d.decision_date, d.project_id
    FROM decisions d
    WHERE d.organization_id = 'bench-org'
    AND d.status IN ('proposed', 'under_review', 'approved')
    ORDER BY d.updated_at DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "Company Context - Decisions", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 5. Company Brain answer (complex multi-entity query)
    # This simulates the Company Brain's multi-entity retrieval
    query = """
    WITH project_cte AS (
        SELECT p.id, p.name, p.code, p.status, p.progress
        FROM projects p
        WHERE p.organization_id = 'bench-org'
        AND p.status = 'active'
        ORDER BY p.updated_at DESC
        LIMIT 10
    ),
    task_cte AS (
        SELECT t.id, t.title, t.status, t.priority, t.project_id
        FROM tasks t
        WHERE t.organization_id = 'bench-org'
        AND t.status IN ('pending', 'in_progress')
        ORDER BY t.updated_at DESC
        LIMIT 20
    ),
    decision_cte AS (
        SELECT d.id, d.title, d.status, d.project_id
        FROM decisions d
        WHERE d.organization_id = 'bench-org'
        AND d.status IN ('proposed', 'under_review')
        ORDER BY d.updated_at DESC
        LIMIT 10
    )
    SELECT * FROM project_cte
    UNION ALL
    SELECT * FROM task_cte
    UNION ALL
    SELECT * FROM decision_cte
    ORDER BY updated_at DESC
    LIMIT 30
    """
    await run_explain_analyze(db, "Company Brain - Multi-entity Context", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    return []


async def run_search_benchmarks(db: AsyncSession) -> List:
    """Run EXPLAIN ANALYZE on Search (FTS) queries."""
    
    print("\n=== FULL-TEXT SEARCH QUERIES ===")
    
    # 1. Basic FTS search
    query = """
    SELECT 
        id, title, content, ts_rank_cd(search_vector, websearch_to_tsquery('english', 'project planning')) as rank
    FROM knowledge_search_index
    WHERE organization_id = 'bench-org'
    AND search_vector @@ websearch_to_tsquery('english', 'project planning')
    ORDER BY rank DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "FTS - Knowledge Search", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 2. Document search
    query = """
    SELECT id, title, category, ts_rank_cd(search_vector, websearch_to_tsquery('english', 'architecture')) as rank
    FROM documents
    WHERE organization_id = 'bench-org'
    AND search_vector @@ websearch_to_tsquery('english', 'architecture')
    AND status = 'published'
    ORDER BY rank DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "FTS - Document Search", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 3. Employee search
    query = """
    SELECT id, display_name, email, designation, department_id
    FROM employees
    WHERE organization_id = 'bench-org'
    AND search_vector @@ websearch_to_tsquery('english', 'engineer')
    AND status = 'active'
    ORDER BY ts_rank_cd(search_vector, websearch_to_tsquery('english', 'engineer')) DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "FTS - Employee Search", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 4. Project search with trigram (fuzzy)
    query = """
    SELECT id, name, code, description
    FROM projects
    WHERE organization_id = 'bench-org'
    AND name % 'project alpha'
    ORDER BY similarity(name, 'project alpha') DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "Trigram - Project Fuzzy Search", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 5. Search + cursor pagination (combined FTS + cursor)
    query = """
    SELECT 
        id, title, ts_rank_cd(search_vector, websearch_to_tsquery('english', 'project')) as rank
    FROM knowledge_search_index
    WHERE organization_id = 'bench-org'
    AND search_vector @@ websearch_to_tsquery('english', 'project')
    AND (search_vector, id) < (
        SELECT search_vector, id FROM knowledge_search_index
        WHERE organization_id = 'bench-org'
        AND search_vector @@ websearch_to_tsquery('english', 'project')
        ORDER BY search_vector DESC, id DESC
        LIMIT 1 OFFSET 5
    )
    ORDER BY search_vector DESC, id DESC
    LIMIT 10
    """
    await run_explain_analyze(db, "FTS + Cursor - Knowledge Search", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    return []


async def run_pagination_benchmarks(db: AsyncSession) -> List:
    """Run EXPLAIN ANALYZE on cursor pagination queries."""
    
    print("\n=== CURSOR PAGINATION QUERIES ===")
    
    # 1. Projects pagination (composite cursor: updated_at + id)
    query = """
    SELECT id, name, code, status, progress, updated_at, id
    FROM projects
    WHERE organization_id = 'bench-org'
    AND status = 'active'
    AND (updated_at < '2026-01-15 12:00:00+00' 
         OR (updated_at = '2026-01-15 12:00:00+00' AND id < 'proj-000005'))
    ORDER BY updated_at DESC, id DESC
    LIMIT 6
    """
    await run_explain_analyze(db, "Cursor Pagination - Projects (composite cursor)", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 2. Tasks pagination (composite cursor: project_id + updated_at + id)
    query = """
    SELECT id, title, status, priority, project_id, updated_at, id
    FROM tasks
    WHERE organization_id = 'bench-org'
    AND project_id = 'proj-000001'
    AND status IN ('pending', 'in_progress')
    AND (updated_at < '2026-01-10 10:00:00+00' 
         OR (updated_at = '2026-01-10 10:00:00+00' AND id < 'task-000005'))
    ORDER BY updated_at DESC, id DESC
    LIMIT 6
    """
    await run_explain_analyze(db, "Cursor Pagination - Tasks (composite cursor)", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 3. Compare OFFSET/LIMIT vs Cursor pagination
    query_offset = """
    SELECT id, title, status, updated_at
    FROM tasks
    WHERE organization_id = 'bench-org'
    ORDER BY updated_at DESC
    LIMIT 20 OFFSET 100000
    """
    await run_explain_analyze(db, "OFFSET Pagination - Tasks (offset 100000)", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query_offset}")
    
    query_cursor = """
    SELECT id, title, status, updated_at
    FROM tasks
    WHERE organization_id = 'bench-org'
    AND (updated_at < '2026-01-15 12:00:00+00' 
         OR (updated_at = '2026-01-15 12:00:00+00' AND id < 'task-000100'))
    ORDER BY updated_at DESC, id DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "Cursor Pagination - Tasks (cursor at 100k)", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query_cursor}")
    
    # 4. Observations pagination (high-volume)
    query = """
    SELECT id, observation_type, severity, observed_at, organization_id
    FROM canonical_observations
    WHERE organization_id = 'bench-org'
    AND observed_at < '2026-01-15 12:00:00+00'
    ORDER BY observed_at DESC, id DESC
    LIMIT 101
    """
    await run_explain_analyze(db, "Cursor Pagination - Observations (high volume)", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 5. Security events pagination
    query = """
    SELECT id, event_type, severity, status, created_at
    FROM security_events
    WHERE organization_id = 'bench-org'
    AND created_at < '2026-01-15 12:00:00+00'
    ORDER BY created_at DESC, id DESC
    LIMIT 51
    """
    await run_explain_analyze(db, "Cursor Pagination - Security Events", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    return []


async def run_integration_benchmarks(db: AsyncSession) -> List:
    """Run EXPLAIN ANALYZE on combined workloads (search + cursor, context + search, etc.)"""
    
    print("\n=== INTEGRATED WORKLOAD QUERIES ===")
    
    # 1. Search + cursor pagination (FTS + cursor)
    query = """
    SELECT 
        id, title, ts_rank_cd(search_vector, websearch_to_tsquery('english', 'project')) as rank
    FROM knowledge_search_index
    WHERE organization_id = 'bench-org'
    AND search_vector @@ websearch_to_tsquery('english', 'project')
    AND (search_vector, id) < (
        SELECT search_vector, id FROM knowledge_search_index
        WHERE organization_id = 'bench-org'
        AND search_vector @@ websearch_to_tsquery('english', 'project')
        ORDER BY search_vector DESC, id DESC
        LIMIT 1 OFFSET 5
    )
    ORDER BY search_vector DESC, id DESC
    LIMIT 10
    """
    await run_explain_analyze(db, "FTS + Cursor - Knowledge Search", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    # 2. Company Brain with cursor (context + search + cursor)
    query = """
    WITH brain_context AS (
        SELECT p.id, p.name, p.code, p.status, p.progress
        FROM projects p
        WHERE p.organization_id = 'bench-org'
        AND p.status = 'active'
        ORDER BY p.updated_at DESC
        LIMIT 10
    ),
    brain_tasks AS (
        SELECT t.id, t.title, t.status, t.priority
        FROM tasks t
        WHERE t.organization_id = 'bench-org'
        AND t.status IN ('pending', 'in_progress')
        ORDER BY t.updated_at DESC
        LIMIT 10
    )
    SELECT * FROM brain_context
    UNION ALL
    SELECT * FROM brain_tasks
    ORDER BY updated_at DESC
    LIMIT 20
    """
    await run_explain_analyze(db, "Company Brain - Context + Tasks", 
        f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
    
    return []


async def run_migration_benchmarks(db: AsyncSession) -> List:
    """Run benchmarks for index migrations and query shape improvements."""
    
    print("\n=== INDEX ENGINEERING VALIDATION ===")
    
    # Check existing indexes
    query = """
    SELECT schemaname, tablename, indexname, indexdef
    FROM pg_indexes
    WHERE schemaname = 'public'
    AND tablename IN ('projects', 'tasks', 'employees', 'documents', 
                      'knowledge_search_index', 'canonical_observations', 
                      'security_events', 'canonical_operations',
                      'company_attentions', 'company_insights')
    ORDER BY tablename, indexname
    """
    result = await db.execute(text(query))
    indexes = result.all()
    
    print(f"\nFound {len(indexes)} indexes on key tables:")
    for idx in indexes:
        print(f"  {idx.tablename}.{idx.indexname}: {idx.indexdef[:80]}...")
    
    return []


async def run_explain_analyze(db: AsyncSession, name: str, query: str) -> None:
    """Helper to run EXPLAIN ANALYZE and print summary."""
    print(f"\n  {name}:")
    print(f"  SQL: {query[:100]}...")
    
    try:
        result = await db.execute(text(query))
        plan = result.scalar()
        
        if isinstance(plan, list):
            plan = plan[0]
        
        plan_data = plan.get('Plan', {})
        total_time = plan.get('Execution Time', 0)
        plan_time = plan.get('Planning Time', 0)
        rows = plan.get('Plan', {}).get('Actual Rows', 0)
        
        print(f"  Planning: {plan_time:.2f}ms, Execution: {total_time:.2f}ms, Rows: {rows}")
        
        # Print key plan details
        plan_data = plan.get('Plan', {})
        if 'Plans' in plan_data:
            for sub in plan_data['Plans']:
                print(f"  {sub.get('Node Type', 'Unknown')}: {sub.get('Actual Rows', 0)} rows, "
                      f"{sub.get('Actual Total Time', 0):.2f}ms, "
                      f"Buffers: hit={sub.get('Shared Hit Blocks', 0)} read={sub.get('Shared Read Blocks', 0)}")
        else:
            print(f"  {plan_data.get('Node Type', 'Unknown')}: {plan_data.get('Actual Rows', 0)} rows, "
                  f"{plan_data.get('Actual Total Time', 0):.2f}ms, "
                  f"Buffers: hit={plan_data.get('Shared Hit Blocks', 0)} read={plan_data.get('Shared Read Blocks', 0)}")
    except Exception as e:
        print(f"  ERROR: {e}")


async def main():
    """Main benchmark runner."""
    print("="*80)
    print("GATE 35-D - QUERY PLAN ENGINEERING BENCHMARK")
    print("="*80)
    print(f"PostgreSQL URL: {PG_URL}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    
    engine = create_async_engine(PG_URL, poolclass=NullPool, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Setup test data
        org_id = "bench-org"
        print("Setting up test data...")
        await setup_test_data(session, org_id, "medium")
        
        # Run benchmarks
        print("\nStarting Gate 35-D benchmarks...")
        
        await run_company_context_benchmarks(session, "bench-org", "user-000000")
        await run_search_benchmarks(session)
        await run_pagination_benchmarks(session)
        await run_integration_benchmarks(session)
        await run_migration_benchmarks(session)
        
        print("\n" + "="*80)
        print("GATE 35-D BENCHMARK COMPLETE")
        print("="*80)
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())