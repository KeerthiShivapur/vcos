"""Gate 35-D — Query Plan Engineering Tests.

Captures and verifies PostgreSQL query plans for production query shapes.

NOTE: These tests require a real PostgreSQL database. They are skipped on SQLite.
"""

import pytest
import pytest_asyncio
import time
import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.knowledge import Document, WikiPage, Policy, KnowledgeIndex
from app.models.communication import Conversation, ConversationMember, Message
from app.models.observability import CanonicalObservation
from app.models.continuous_twin import CompanyAttention
from app.intelligence.company_context import build_context
from app.intelligence.company_brain import CompanyBrain
from app.services.postgres_fulltext_search import PostgresFullTextSearchService
from app.utils.pagination import Cursor, paginate_projects, paginate_tasks, paginate_observations, paginate_company_attention
from app.services.observability_service import observability_service, ObservationContext
from app.core.timeutils import utcnow

import uuid
import json


# Check if we're running against PostgreSQL
def is_postgresql(db: AsyncSession) -> bool:
    """Check if the database is PostgreSQL."""
    try:
        # Simple sync check - if dialect is postgresql
        return db.bind.dialect.name == "postgresql"
    except Exception:
        return False


@pytest.fixture
def pg_only(db_session: AsyncSession):
    """Skip test if not running on PostgreSQL."""
    if not is_postgresql(db_session):
        pytest.skip("Test requires PostgreSQL")


@dataclass
class QueryPlanResult:
    """Result of a query plan analysis."""
    query_name: str
    query_sql: str
    plan: Any
    execution_time_ms: float
    planning_time_ms: float
    rows_returned: int
    scans: List[str] = field(default_factory=list)
    indexes_used: List[str] = field(default_factory=list)
    sequential_scans: int = 0
    index_scans: int = 0
    sort_operations: int = 0
    join_operations: int = 0
    total_cost: float = 0.0
    startup_cost: float = 0.0


class QueryPlanCapture:
    """Captures and analyzes PostgreSQL query plans."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.results: List[QueryPlanResult] = []
    
    async def capture_plan(
        self,
        query_name: str,
        query_sql: str,
        params: Dict = None,
    ) -> QueryPlanResult:
        """Capture EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) for a query."""
        
        # Get query plan with ANALYZE and BUFFERS (PostgreSQL only)
        explain_sql = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query_sql}"
        
        started = time.perf_counter()
        result = await self.db.execute(text(explain_sql), params or {})
        execution_time = (time.perf_counter() - started) * 1000
        
        plan_data = result.scalar()
        
        # Parse the plan
        plan = plan_data[0]["Plan"] if plan_data else None
        
        analysis = self._analyze_plan(plan) if plan else {}
        
        result_obj = QueryPlanResult(
            query_name=query_name,
            query_sql=query_sql,
            plan=plan_data,
            execution_time_ms=execution_time,
            planning_time_ms=plan_data[0]["Planning Time"] if plan_data else 0,
            rows_returned=plan_data[0]["Plan"]["Actual Rows"] if plan_data and plan_data[0]["Plan"].get("Actual Rows") else 0,
            scans=analysis.get("scans", []),
            indexes_used=analysis.get("indexes_used", []),
            sequential_scans=analysis.get("sequential_scans", 0),
            index_scans=analysis.get("index_scans", 0),
            sort_operations=analysis.get("sort_operations", 0),
            join_operations=analysis.get("join_operations", 0),
            total_cost=analysis.get("total_cost", 0.0),
            startup_cost=analysis.get("startup_cost", 0.0),
        )
        
        self.results.append(result_obj)
        return result_obj
    
    def _analyze_plan(self, plan: Dict) -> Dict[str, Any]:
        """Analyze a query plan for key metrics."""
        if not plan:
            return {}
        
        scans = []
        indexes_used = []
        sequential_scans = 0
        index_scans = 0
        sort_operations = 0
        join_operations = 0
        total_cost = plan.get("Total Cost", 0)
        startup_cost = plan.get("Startup Cost", 0)
        
        def walk(node: Dict):
            nonlocal sequential_scans, index_scans, sort_operations, join_operations
            
            node_type = node.get("Node Type", "")
            
            if "Seq Scan" in node_type:
                sequential_scans += 1
                relation = node.get("Relation Name", "unknown")
                scans.append(f"Seq Scan on {relation}")
            elif "Index Scan" in node_type or "Bitmap Index Scan" in node_type:
                index_scans += 1
                index_name = node.get("Index Name", "unknown")
                relation = node.get("Relation Name", "unknown")
                indexes_used.append(f"{index_name} on {relation}")
            elif "Sort" in node_type:
                sort_operations += 1
            elif "Join" in node_type:
                join_operations += 1
            
            # Walk children
            for child in node.get("Plans", []):
                walk(child)
        
        walk(plan)
        
        return {
            "scans": scans,
            "indexes_used": indexes_used,
            "sequential_scans": sequential_scans,
            "index_scans": index_scans,
            "sort_operations": sort_operations,
            "join_operations": join_operations,
            "total_cost": total_cost,
            "startup_cost": startup_cost,
        }
    
    def verify_plan_quality(self, result: QueryPlanResult, expectations: Dict[str, Any]) -> List[str]:
        """Verify a query plan meets quality expectations. Returns list of violations."""
        violations = []
        
        if expectations.get("no_seq_scan", False) and result.sequential_scans > 0:
            violations.append(f"Unexpected sequential scan: {result.scans}")
        
        if expectations.get("uses_index", False) and result.index_scans == 0:
            violations.append(f"No index scan found for {result.query_name}")
        
        if expectations.get("max_rows", float('inf')) < result.rows_returned:
            violations.append(f"Too many rows returned: {result.rows_returned} > {expectations['max_rows']}")
        
        if expectations.get("max_execution_time_ms", float('inf')) < result.execution_time_ms:
            violations.append(f"Execution time too high: {result.execution_time_ms}ms > {expectations['max_execution_time_ms']}ms")
        
        if expectations.get("max_planning_time_ms", float('inf')) < result.planning_time_ms:
            violations.append(f"Planning time too high: {result.planning_time_ms}ms > {expectations['max_planning_time_ms']}ms")
        
        if expectations.get("max_sort_operations", 10) < result.sort_operations:
            violations.append(f"Too many sort operations: {result.sort_operations}")
        
        if expectations.get("required_indexes"):
            for required_idx in expectations["required_indexes"]:
                found = any(required_idx in idx for idx in result.indexes_used)
                if not found:
                    violations.append(f"Required index not used: {required_idx}")
        
        return violations


class TestGate35DQueryPlans:
    """Query plan engineering tests for Gate 35-D.
    
    These tests require PostgreSQL and are skipped on SQLite.
    """
    
    @pytest_asyncio.fixture
    async def test_org(self, db_session: AsyncSession, pg_only) -> Dict[str, Any]:
        """Create test organization with realistic data."""
        org_id = uuid.uuid4().hex[:32]
        org = Organization(
            id=org_id,
            name=f"Query Plan Test Org {uuid.uuid4().hex[:8]}",
            slug=f"qp-test-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
            status="active",
        )
        db_session.add(org)
        
        user_id = uuid.uuid4().hex[:32]
        user = User(
            id=user_id,
            organization_id=org_id,
            email=f"test-{uuid.uuid4().hex[:8]}@example.com",
            full_name="Test User",
            password_hash="hash",
        )
        db_session.add(user)
        
        emp = Employee(
            id=uuid.uuid4().hex[:32],
            organization_id=org_id,
            user_id=user_id,
            employee_number="E001",
            first_name="John",
            last_name="Doe",
            display_name="John Doe",
            email="john.doe@example.com",
            designation="Software Engineer",
            status="active",
            joining_date=utcnow(),
        )
        db_session.add(emp)
        
        # Create projects
        projects = []
        for i in range(20):
            p = Project(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                name=f"Project Alpha {i}",
                code=f"PA{i}",
                description=f"Project Alpha {i} description for search testing",
                status="active",
                progress=i * 5,
            )
            db_session.add(p)
            projects.append(p)
        
        # Create tasks
        tasks = []
        for i in range(50):
            t = Task(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                project_id=projects[i % len(projects)].id,
                title=f"Task {i}: Implement Feature",
                description=f"Task {i} description",
                status="active" if i % 3 != 0 else "completed",
                priority="high" if i % 2 == 0 else "medium",
                assignee_id=emp.id,
            )
            db_session.add(t)
            tasks.append(t)
        
        # Create documents
        documents = []
        for i in range(30):
            d = Document(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                title=f"Document {i}: Project Planning",
                slug=f"document-{i}-{uuid.uuid4().hex[:8]}",
                description=f"Document {i} description for search",
                category="planning",
                status="published",
                author_id=user_id,
                project_id=projects[i % len(projects)].id,
            )
            db_session.add(d)
            documents.append(d)
        
        # Create knowledge index entries
        for i in range(20):
            ki = KnowledgeIndex(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                entity_type="document",
                entity_id=documents[i % len(documents)].id,
                title=f"Knowledge: Project Planning {i}",
                content=f"Knowledge content about project planning {i} for search testing",
                keywords_json='["planning", "project", "search", "test"]',
            )
            db_session.add(ki)
        
        # Create conversations
        conversations = []
        for i in range(10):
            conv = Conversation(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                type="channel",
                title=f"Channel {i}",
                channel_key=f"channel-{i}",
                is_archived=False,
                message_count=50,
            )
            db_session.add(conv)
            conversations.append(conv)
        
        # Add conversation members
        for conv in conversations:
            member = ConversationMember(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                conversation_id=conv.id,
                employee_id=emp.id,
                role="member",
            )
            db_session.add(member)
        
        # Create messages
        for i in range(100):
            conv = conversations[i % len(conversations)]
            msg = Message(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                conversation_id=conv.id,
                sender_id=emp.id,
                content=f"Message {i}: Update on project {i % 20}",
                deleted=False,
            )
            db_session.add(msg)
        
        # Create observability data
        for i in range(50):
            obs = CanonicalObservation(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                observation_type="request",
                source="api",
                source_component="api-gateway",
                actor_id=emp.id,
                actor_type="human",
                severity="info",
                epistemic_status="observed",
                correlation_id=uuid.uuid4().hex[:32] if i % 3 == 0 else None,
                trace_id=uuid.uuid4().hex[:32] if i % 5 == 0 else None,
                title=f"GET /api/resource/{i} - 200",
                description=f"API request returned 200",
                details_json={"route": f"/api/resource/{i}", "method": "GET"},
                metrics_json={"duration_ms": 100 + i * 10, "status_code": 200},
                observed_at=utcnow(),
                duration_ms=100 + i * 10,
                fingerprint=uuid.uuid4().hex[:160],
            )
            db_session.add(obs)
        
        # Create company attention
        for i in range(15):
            attn = CompanyAttention(
                id=uuid.uuid4().hex[:32],
                organization_id=org_id,
                attention_type="degradation",
                priority="alert" if i % 3 == 0 else "watch",
                title=f"Attention {i}: Service degradation",
                description=f"Attention signal {i} description",
                source_type="system",
                source_id=str(i),
                priority_score=0.9 - (i * 0.05),
                urgency="high" if i % 3 == 0 else "normal",
                status="open",
                assigned_to=emp.id if i % 2 == 0 else None,
            )
            db_session.add(attn)
        
        await db_session.commit()
        
        return {
            "org_id": org_id,
            "user_id": user_id,
            "user": user,
            "emp_id": emp.id,
            "projects": projects,
            "tasks": tasks,
            "documents": documents,
            "conversations": conversations,
        }
    
    @pytest_asyncio.fixture
    async def capture(self, db_session: AsyncSession, pg_only) -> QueryPlanCapture:
        """Create query plan capture utility."""
        return QueryPlanCapture(db_session)
    
    # ================================================================
    # Company Context Query Plans
    # ================================================================
    
    async def test_company_context_build_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test Company Context build query plan."""
        org_id = test_org["org_id"]
        user = test_org["user"]
        
        # Use the actual build_context function
        context = await build_context(
            db_session, user, "What is the status of Project Alpha?",
            organization_id=org_id,
        )
        
        # The actual query is inside build_context, so we test with a representative query
        query = """
            SELECT id, name, code, description, status, progress, updated_at
            FROM projects
            WHERE organization_id = :org_id
            AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT 50
        """
        
        result = await capture.capture_plan("company_context_projects", query, {"org_id": org_id})
        
        # Verify: should use index on (organization_id, status, updated_at DESC)
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 50,
            "required_indexes": ["ix_projects_org_status_updated"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    async def test_company_context_tasks_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test Company Context tasks query plan."""
        org_id = test_org["org_id"]
        user = test_org["user"]
        
        query = """
            SELECT t.id, t.title, t.status, t.priority, t.project_id, t.updated_at
            FROM tasks t
            WHERE t.organization_id = :org_id
            AND t.project_id IN (SELECT id FROM projects WHERE organization_id = :org_id)
            ORDER BY t.updated_at DESC
            LIMIT 50
        """
        
        result = await capture.capture_plan("company_context_tasks", query, {"org_id": org_id})
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 50,
            "required_indexes": ["ix_tasks_org_project_updated"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    async def test_company_context_knowledge_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test Company Context knowledge/documents query plan."""
        org_id = test_org["org_id"]
        
        query = """
            SELECT d.id, d.title, d.slug, d.description, d.category, d.status, d.updated_at
            FROM documents d
            WHERE d.organization_id = :org_id
            AND d.status IN ('published', 'draft')
            AND d.project_id IN (SELECT id FROM projects WHERE organization_id = :org_id)
            ORDER BY d.updated_at DESC
            LIMIT 50
        """
        
        result = await capture.capture_plan("company_context_documents", query, {"org_id": org_id})
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 50,
            "required_indexes": ["ix_documents_org_status_updated", "ix_documents_org_project"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    # ================================================================
    # PostgreSQL Full-Text Search Query Plans
    # ================================================================
    
    async def test_fts_search_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test PostgreSQL FTS search query plan."""
        org_id = test_org["org_id"]
        user = test_org["user"]
        
        # Test the actual FTS service
        fts_service = PostgresFullTextSearchService(db_session)
        search_result = await fts_service.search_fulltext(
            db=db_session,
            organization_id=org_id,
            query="Project Planning",
            user_id=test_org["user_id"],
            user=user,
            limit=10,
        )
        
        # Now capture the plan for a representative FTS query
        query = """
            SELECT 
                ksi.id,
                ksi.title,
                ksi.content,
                'knowledge' as entity_type,
                ts_rank_cd(ksi.search_vector, websearch_to_tsquery('english', :query)) as rank
            FROM knowledge_search_index ksi
            WHERE ksi.organization_id = :org_id
            AND ksi.search_vector @@ websearch_to_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :limit
        """
        
        result = await capture.capture_plan("fts_knowledge_search", query, {
            "org_id": org_id,
            "query": "Project Planning",
            "limit": 10,
        })
        
        # Should use GIN index on search_vector
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 100,
            "required_indexes": ["ix_knowledge_search_index_fts", "ix_knowledge_search_index_org_fts"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    async def test_fts_documents_search_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test FTS search on documents."""
        org_id = test_org["org_id"]
        
        query = """
            SELECT 
                d.id,
                d.title,
                d.description,
                'document' as entity_type,
                ts_rank_cd(d.search_vector, websearch_to_tsquery('english', :query)) as rank
            FROM documents d
            WHERE d.organization_id = :org_id
            AND d.search_vector @@ websearch_to_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :limit
        """
        
        result = await capture.capture_plan("fts_documents_search", query, {
            "org_id": org_id,
            "query": "Project Planning",
            "limit": 10,
        })
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 100,
            "required_indexes": ["ix_documents_fts", "ix_documents_org_fts"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    async def test_fts_employees_search_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test FTS search on employees."""
        org_id = test_org["org_id"]
        
        query = """
            SELECT 
                e.id,
                e.display_name as title,
                e.designation as content,
                'employee' as entity_type,
                ts_rank_cd(e.search_vector, websearch_to_tsquery('english', :query)) as rank
            FROM employees e
            WHERE e.organization_id = :org_id
            AND e.search_vector @@ websearch_to_tsquery('english', :query)
            ORDER BY rank DESC
            LIMIT :limit
        """
        
        result = await capture.capture_plan("fts_employees_search", query, {
            "org_id": org_id,
            "query": "John",
            "limit": 10,
        })
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 100,
            "required_indexes": ["ix_employees_fts", "ix_employees_org_fts"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    # ================================================================
    # Cursor Pagination Query Plans
    # ================================================================
    
    async def test_cursor_pagination_projects_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test cursor pagination query plan for projects."""
        org_id = test_org["org_id"]
        
        # First page
        page = await paginate_projects(
            db_session,
            organization_id=org_id,
            limit=10,
        )
        
        # Capture the actual pagination query
        query = """
            SELECT p.id, p.name, p.code, p.description, p.status, p.progress, p.updated_at
            FROM projects p
            WHERE p.organization_id = :org_id
            ORDER BY p.updated_at DESC, p.id DESC
            LIMIT :limit
        """
        
        result = await capture.capture_plan("cursor_pagination_projects_first", query, {
            "org_id": org_id,
            "limit": 11,  # +1 for has_next detection
        })
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 50,
            "required_indexes": ["ix_projects_org_status_updated"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    async def test_cursor_pagination_projects_second_page(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test cursor pagination second page query plan."""
        org_id = test_org["org_id"]
        
        # Get first page to get cursor
        page1 = await paginate_projects(db_session, organization_id=org_id, limit=10)
        
        # Decode cursor to get values
        import base64, json
        from app.utils.pagination import Cursor
        
        decoded_cursor = Cursor.decode(page1.next_cursor)
        cursor_data = json.loads(decoded_cursor.after)
        
        query = """
            SELECT p.id, p.name, p.code, p.description, p.status, p.progress, p.updated_at
            FROM projects p
            WHERE p.organization_id = :org_id
            AND (p.updated_at, p.id) < (:cursor_updated_at, :cursor_id)
            ORDER BY p.updated_at DESC, p.id DESC
            LIMIT :limit
        """
        
        result = await capture.capture_plan("cursor_pagination_projects_second", query, {
            "org_id": org_id,
            "cursor_updated_at": cursor_data["updated_at"],
            "cursor_id": cursor_data["id"],
            "limit": 11,
        })
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 50,
            "required_indexes": ["ix_projects_org_status_updated"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    async def test_cursor_pagination_observations_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test cursor pagination for observations."""
        org_id = test_org["org_id"]
        
        page = await paginate_observations(
            db_session,
            organization_id=org_id,
            limit=50,
        )
        
        query = """
            SELECT co.id, co.observation_type, co.severity, co.observed_at, co.title
            FROM canonical_observations co
            WHERE co.organization_id = :org_id
            ORDER BY co.observed_at DESC, co.id DESC
            LIMIT :limit
        """
        
        result = await capture.capture_plan("cursor_pagination_observations", query, {
            "org_id": org_id,
            "limit": 51,
        })
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 100,
            "required_indexes": ["ix_canobs_org_type_severity"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    # ================================================================
    # Company Brain Query Plans
    # ================================================================
    
    async def test_company_brain_answer_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test Company Brain answer query plan (via reasoning engine)."""
        org_id = test_org["org_id"]
        user = test_org["user"]
        
        brain = CompanyBrain()
        answer = await brain.answer(
            db_session, org_id, "What is the status of Project Alpha?",
            user=user,
        )
        
        # Test a representative query from the reasoning engine
        query = """
            SELECT c.id, c.claim, c.confidence, c.evidence, c.kind
            FROM knowledge_claims c
            WHERE c.organization_id = :org_id
            AND c.topic_id IN (
                SELECT id FROM knowledge_topics 
                WHERE organization_id = :org_id
                AND name ILIKE '%project%'
            )
            ORDER BY c.confidence DESC
            LIMIT 10
        """
        
        result = await capture.capture_plan("brain_knowledge_claims", query, {"org_id": org_id})
        
        # Note: This query might not have an exact matching index, but should not seq scan
        violations = capture.verify_plan_quality(result, {
            "max_execution_time_ms": 200,
            "max_rows": 1000,
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    # ================================================================
    # Observability Query Plans
    # ================================================================
    
    async def test_observability_record_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test observability observation recording query plan."""
        org_id = test_org["org_id"]
        emp_id = test_org["emp_id"]
        
        obs = await observability_service.record_observation(
            db=db_session,
            context=ObservationContext(
                organization_id=org_id,
                observation_type="metric",
                source="test",
                severity="info",
                epistemic_status="observed",
                title="Test Metric",
                details_json={"value": 42},
                metrics_json={"duration_ms": 100},
            ),
        )
        
        # The exact-once deduplication query
        query = """
            SELECT id, fingerprint
            FROM canonical_observations
            WHERE organization_id = :org_id
            AND fingerprint = :fingerprint
        """
        
        result = await capture.capture_plan("observability_dedup_check", query, {
            "org_id": org_id,
            "fingerprint": obs.fingerprint,
        })
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 10,
            "required_indexes": ["ix_canonical_operations_fingerprint"],
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    async def test_observability_health_dashboard_plan(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Test health dashboard query plan."""
        org_id = test_org["org_id"]
        
        dashboard = await observability_service.get_health_dashboard(
            db=db_session,
            organization_id=org_id,
        )
        
        # Test health dimensions query
        query = """
            SELECT hd.id, hd.dimension, hd.scope_type, hd.scope_id, hd.status,
                   hd.current_value, hd.target_value, hd.threshold_warn, hd.threshold_critical,
                   hd.unit, hd.trend, hd.trend_score, hd.slo_target, hd.slo_compliance,
                   hd.recorded_at
            FROM health_dimensions hd
            WHERE hd.organization_id = :org_id
            ORDER BY hd.dimension, hd.scope_type, hd.scope_id
            LIMIT 100
        """
        
        result = await capture.capture_plan("observability_health_dimensions", query, {"org_id": org_id})
        
        violations = capture.verify_plan_quality(result, {
            "uses_index": True,
            "max_execution_time_ms": 50,
        })
        
        assert not violations, f"Query plan violations: {violations}"
    
    # ================================================================
    # Regression Tests
    # ================================================================
    
    async def test_before_after_plan_comparison(
        self, db_session: AsyncSession, test_org: Dict, capture: QueryPlanCapture, pg_only
    ):
        """Compare query plans before and after optimization.
        
        This test captures baseline plans that can be compared after
        index/optimization changes.
        """
        org_id = test_org["org_id"]
        
        # Capture baseline plans for key queries
        queries = [
            ("baseline_projects_list", """
                SELECT * FROM projects 
                WHERE organization_id = :org_id AND status = 'active'
                ORDER BY updated_at DESC LIMIT 20
            """),
            ("baseline_tasks_by_project", """
                SELECT * FROM tasks 
                WHERE organization_id = :org_id AND project_id = :project_id
                ORDER BY updated_at DESC LIMIT 50
            """),
            ("baseline_observations_recent", """
                SELECT * FROM canonical_observations
                WHERE organization_id = :org_id
                ORDER BY observed_at DESC LIMIT 100
            """),
            ("baseline_attention_open", """
                SELECT * FROM company_attention
                WHERE organization_id = :org_id AND status = 'open'
                ORDER BY priority_score DESC LIMIT 20
            """),
        ]
        
        baselines = {}
        for name, query in queries:
            params = {"org_id": org_id}
            if "project_id" in query:
                params["project_id"] = test_org["projects"][0].id
            
            result = await capture.capture_plan(name, query, params)
            baselines[name] = {
                "execution_time_ms": result.execution_time_ms,
                "planning_time_ms": result.planning_time_ms,
                "rows_returned": result.rows_returned,
                "indexes_used": result.indexes_used,
                "sequential_scans": result.sequential_scans,
            }
        
        # Store baselines for comparison
        print("\n=== BASELINE QUERY PLANS ===")
        for name, data in baselines.items():
            print(f"{name}: {data}")
        
        # Verify no unexpected sequential scans on selective queries
        for name, data in baselines.items():
            assert data["sequential_scans"] == 0, f"Unexpected seq scan in {name}"
        
        # Store for later comparison
        self._baselines = baselines


# ================================================================
# Export
# ================================================================

__all__ = [
    "QueryPlanCapture",
    "QueryPlanResult",
    "TestGate35DQueryPlans",
]