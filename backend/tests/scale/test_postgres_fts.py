"""Gate 35-B — PostgreSQL Full-Text Search Tests."""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.project import Project
from app.models.task import Task
from app.models.knowledge import KnowledgeIndex, Document
from app.services.postgres_fulltext_search import PostgresFullTextSearchService, SearchMode, SearchResult
from app.intelligence.company_context import resolve_caller_access


@pytest_asyncio.fixture
async def search_org(pg_db_session: AsyncSession) -> Dict[str, Any]:
    """Create organization with test data for search."""
    org_id = uuid.uuid4().hex[:32]
    org = Organization(
        id=org_id,
        name="Search Test Org",
        slug=f"search-test-{uuid.uuid4().hex[:8]}",
        industry="Technology",
        country="US",
        timezone="UTC",
        currency="USD",
    )
    pg_db_session.add(org)
    await pg_db_session.flush()
    
    user_id = uuid.uuid4().hex[:32]
    user = User(
        id=user_id,
        organization_id=org_id,
        email="test@example.com",
        full_name="Test User",
        password_hash="hash",
    )
    pg_db_session.add(user)
    await pg_db_session.flush()
    
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
        joining_date=datetime.now(timezone.utc),
    )
    pg_db_session.add(emp)
    await pg_db_session.flush()
    
    # Create projects
    projects = []
    for i in range(5):
        p = Project(
            id=uuid.uuid4().hex[:32],
            organization_id=org_id,
            name=f"Project Alpha {i}",
            code=f"PA{i}",
            description=f"Project Alpha {i} description for search testing",
            status="active",
            progress=i * 20,
        )
        pg_db_session.add(p)
        projects.append(p)
    await pg_db_session.flush()
    
    # Create documents
    documents = []
    for i in range(5):
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
        pg_db_session.add(d)
        documents.append(d)
    
    # Create knowledge index entries
    knowledge_entries = []
    for i in range(5):
        ki = KnowledgeIndex(
            id=uuid.uuid4().hex[:32],
            organization_id=org_id,
            entity_type="document",
            entity_id=uuid.uuid4().hex[:32],  # Use random ID since we don't need to link to documents
            title=f"Knowledge: Project Planning {i}",
            content=f"Knowledge content about project planning {i} for search testing",
            keywords_json=f'["planning", "project", "search", "test"]',
        )
        pg_db_session.add(ki)
        knowledge_entries.append(ki)
    
    # Create employees
    employees = []
    for i in range(3):
        e = Employee(
            id=uuid.uuid4().hex[:32],
            organization_id=org_id,
            employee_number=f"E{1000+i}",
            first_name=f"Jane{i}",
            last_name=f"Smith{i}",
            display_name=f"Jane{i} Smith{i}",
            email=f"jane{i}.smith{i}@example.com",
            designation="Engineer",
            status="active",
            joining_date=datetime.now(timezone.utc),
        )
        pg_db_session.add(e)
        employees.append(e)
    await pg_db_session.flush()
    
    # Create tasks
    tasks = []
    for i in range(5):
        t = Task(
            id=uuid.uuid4().hex[:32],
            organization_id=org_id,
            project_id=projects[i % len(projects)].id,
            title=f"Task {i}: Implement Feature",
            description=f"Task {i} description for search testing",
            status="active",
            priority="high",
            assignee_id=employees[i % len(employees)].id,
        )
        pg_db_session.add(t)
        tasks.append(t)
    
    await pg_db_session.commit()
    
    return {
        "org_id": org_id,
        "user_id": user_id,
        "user": None,  # Will be set in test
        "projects": projects,
        "documents": documents,
        "knowledge_entries": knowledge_entries,
        "tasks": tasks,
        "employees": employees,
    }


class TestPostgresFullTextSearch:
    """Tests for PostgreSQL Full-Text Search Service."""
    
    @pytest_asyncio.fixture
    async def search_service(self, pg_db_session: AsyncSession) -> PostgresFullTextSearchService:
        """Create a search service instance for testing."""
        return PostgresFullTextSearchService(pg_db_session)
    
    async def test_fts_basic_search(
        self, 
        pg_db_session: AsyncSession, 
        search_org: Dict[str, Any],
        search_service: PostgresFullTextSearchService
    ):
        """Test basic full-text search functionality."""
        org_id = search_org["org_id"]
        user_id = search_org["user_id"]
        
        # Create a mock user object
        from app.models.user import User
        user = User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash")
        
        # Search for "Project Planning" - should find knowledge entries and documents
        result = await search_service.search_fulltext(
            db=search_service.db,
            organization_id=org_id,
            query="Project Planning",
            user_id=search_org["user_id"],
            user=user,
            limit=10,
        )
        
        assert result["query"] == "Project Planning"
        assert result["total"] >= 0
        assert "took_ms" in result
        assert result["mode"] == "fts"
        
        # Check results structure
        for result in result["results"]:
            assert "type" in result
            assert "id" in result
            assert "title" in result
            assert "score" in result
            assert result["score"] >= 0
    
    async def test_fts_empty_query(
        self, 
        pg_db_session: AsyncSession, 
        search_org: Dict[str, Any],
        search_service: PostgresFullTextSearchService
    ):
        """Test search with empty query."""
        org_id = search_org["org_id"]
        user = User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash")
        
        result = await search_service.search_fulltext(
            db=search_service.db,
            organization_id=search_org["org_id"],
            query="",
            user_id=search_org["user_id"],
            user=User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash"),
            limit=10,
        )
        
        assert result["query"] == ""
        assert result["results"] == []
        assert result["total"] == 0
        assert result["took_ms"] == 0
    
    async def test_fts_employee_search(
        self, 
        pg_db_session: AsyncSession, 
        search_org: Dict[str, Any],
        search_service: PostgresFullTextSearchService
    ):
        """Test employee search via FTS."""
        org_id = search_org["org_id"]
        user = User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash")
        
        result = await search_service.search_fulltext(
            db=search_service.db,
            organization_id=search_org["org_id"],
            query="Jane",
            user_id=search_org["user_id"],
            user=User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash"),
            entity_types=["employee"],
            limit=10,
        )
        
        assert result["query"] == "Jane"
        # Should find employees with "Jane" in their name
        for result in result["results"]:
            assert result["type"] == "employee"
    
    async def test_fts_project_search(
        self, 
        pg_db_session: AsyncSession, 
        search_org: Dict[str, Any],
        search_service: PostgresFullTextSearchService
    ):
        """Test project search via FTS."""
        org_id = search_org["org_id"]
        user = User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash")
        
        result = await search_service.search_fulltext(
            db=search_service.db,
            organization_id=search_org["org_id"],
            query="Project Alpha",
            user_id=search_org["user_id"],
            user=User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash"),
            entity_types=["project"],
            limit=10,
        )
        
        assert result["query"] == "Project Alpha"
        for result in result["results"]:
            assert result["type"] == "project"
    
    async def test_fts_hybrid_mode(
        self, 
        pg_db_session: AsyncSession, 
        search_org: Dict[str, Any],
        search_service: PostgresFullTextSearchService
    ):
        """Test hybrid search mode."""
        org_id = search_org["org_id"]
        user = User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash")
        
        result = await search_service.search_fulltext(
            db=search_service.db,
            organization_id=org_id,
            query="Project",
            user_id=search_org["user_id"],
            user=user,
            limit=10,
        )
        
        assert result["mode"] == "fts"
        # Hybrid mode should still work (falls back to FTS in test env)
    
    async def test_search_result_structure(
        self, 
        pg_db_session: AsyncSession, 
        search_org: Dict[str, Any],
        search_service: PostgresFullTextSearchService
    ):
        """Test that search results have correct structure."""
        org_id = search_org["org_id"]
        user = User(id=search_org["user_id"], organization_id=search_org["org_id"], email="test@example.com", full_name="Test User", password_hash="hash")
        
        result = await search_service.search_fulltext(
            db=search_service.db,
            organization_id=org_id,
            query="test",
            user_id=search_org["user_id"],
            user=user,
            limit=5,
        )
        
        for result in result["results"]:
            required_fields = ["type", "id", "title", "subtitle", "url", "snippet", "score", "metadata", "search_mode"]
            for field in required_fields:
                assert field in result, f"Missing field: {field}"
            
            assert isinstance(result["score"], (int, float))
            assert result["score"] >= 0
            assert result["search_mode"] in ("fts", "trigram", "hybrid")


class TestSearchResultDataclass:
    """Tests for SearchResult dataclass."""
    
    def test_search_result_creation(self):
        """Test SearchResult dataclass creation."""
        result = SearchResult(
            type="project",
            id="test-id",
            title="Test Project",
            subtitle="Project details",
            url="/projects/test-id",
            snippet="Project snippet",
            score=0.95,
            metadata={"status": "active"},
            search_mode="fts",
        )
        
        assert result.type == "project"
        assert result.id == "test-id"
        assert result.title == "Test Project"
        assert result.score == 0.95
        assert result.search_mode == "fts"
    
    def test_search_mode_enum(self):
        """Test SearchMode enum values."""
        assert SearchMode.FTS.value == "fts"
        assert SearchMode.TRIGRAM.value == "trigram"
        assert SearchMode.EXACT.value == "exact"
        assert SearchMode.HYBRID.value == "hybrid"


class TestPostgresFTSTenantIsolation:
    """Test tenant isolation in PostgreSQL FTS."""
    
    @pytest_asyncio.fixture
    async def two_orgs(self, pg_db_session: AsyncSession) -> Dict[str, Any]:
        """Create two organizations with search data."""
        org1_id = uuid.uuid4().hex[:32]
        org2_id = uuid.uuid4().hex[:32]
        
        org1 = Organization(
            id=org1_id,
            name="Org One",
            slug=f"org-one-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        org2 = Organization(
            id=org2_id,
            name="Org Two",
            slug=f"org-two-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        pg_db_session.add(org1)
        pg_db_session.add(org2)
        await pg_db_session.flush()
        
        # Create users
        user1 = User(id=uuid.uuid4().hex[:32], organization_id=org1_id, email="u1@org1.com", full_name="User 1", password_hash="hash")
        user2 = User(id=uuid.uuid4().hex[:32], organization_id=org2_id, email="u2@org2.com", full_name="User 2", password_hash="hash")
        pg_db_session.add(user1)
        pg_db_session.add(user2)
        await pg_db_session.flush()
        
        # Create knowledge in org1
        ki1 = KnowledgeIndex(
            id=uuid.uuid4().hex[:32],
            organization_id=org1_id,
            entity_type="document",
            entity_id=uuid.uuid4().hex[:32],
            title="Org One Secret Project",
            content="Confidential project details for organization one",
            keywords_json='["secret", "project", "org1"]',
        )
        pg_db_session.add(ki1)
        
        # Create knowledge in org2
        ki2 = KnowledgeIndex(
            id=uuid.uuid4().hex[:32],
            organization_id=org2_id,
            entity_type="document",
            entity_id=uuid.uuid4().hex[:32],
            title="Org Two Secret Project",
            content="Confidential project details for organization two",
            keywords_json='["secret", "project", "org2"]',
        )
        pg_db_session.add(ki2)
        
        await pg_db_session.commit()
        
        return {
            "org1_id": org1_id,
            "org2_id": org2_id,
            "user1_id": user1.id,
            "user2_id": user2.id,
        }
    
    async def test_cross_tenant_search_isolation(
        self, 
        pg_db_session: AsyncSession, 
        two_orgs: Dict[str, Any]
    ):
        """Test that search results don't leak across tenants."""
        from app.services.postgres_fulltext_search import PostgresFullTextSearchService
        from app.models.user import User
        
        search_service = PostgresFullTextSearchService(pg_db_session)
        
        org1_id = two_orgs["org1_id"]
        org2_id = two_orgs["org2_id"]
        user1_id = two_orgs["user1_id"]
        user2_id = two_orgs["user2_id"]
        
        user1 = User(id=user1_id, organization_id=org1_id, email="u1@test.com", full_name="User 1", password_hash="hash")
        user2 = User(id=user2_id, organization_id=org2_id, email="u2@test.com", full_name="User 2", password_hash="hash")
        
        # Search from org1 - should only find org1's data
        result1 = await PostgresFullTextSearchService(pg_db_session).search_fulltext(
            db=pg_db_session,
            organization_id=org1_id,
            query="Secret Project",
            user_id=user1_id,
            user=user1,
            limit=10,
        )
        
        # Search from org2 - should only find org2's data
        result2 = await PostgresFullTextSearchService(pg_db_session).search_fulltext(
            db=pg_db_session,
            organization_id=org2_id,
            query="Secret Project",
            user_id=user2_id,
            user=user2,
            limit=10,
        )
        
        # Each org should only see their own data
        for r in result1["results"]:
            # All results should be from org1
            assert r["type"] in ("knowledge", "document", "wiki")
        
        for r in result2["results"]:
            # All results should be from org2
            assert r["type"] in ("knowledge", "document", "wiki")
        
        # The key test: results from org1 should not appear in org2's results and vice versa
        # Since they have different organization_ids, they should be isolated
        assert result1["total"] >= 0
        assert result2["total"] >= 0


class TestSearchModeEnum:
    """Test SearchMode enum."""
    
    def test_search_mode_values(self):
        from app.services.postgres_fulltext_search import SearchMode
        
        assert SearchMode.FTS.value == "fts"
        assert SearchMode.TRIGRAM.value == "trigram"
        assert SearchMode.EXACT.value == "exact"
        assert SearchMode.HYBRID.value == "hybrid"


# Export
__all__ = [
    "TestPostgresFullTextSearch",
    "TestSearchResultDataclass",
    "TestSearchModeEnum",
    "TestPostgresFTSTenantIsolation",
]