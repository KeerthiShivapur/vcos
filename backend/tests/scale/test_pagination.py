"""Tests for cursor pagination utilities."""

import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.utils.pagination import (
    Cursor,
    Page,
    CursorPaginator,
    paginate_projects,
    paginate_tasks,
    paginate_observations,
    paginate_company_attention,
)


class TestCursor:
    """Test cursor encoding/decoding."""
    
    def test_encode_decode(self):
        cursor = Cursor(after="abc123", limit=20)
        encoded = cursor.encode()
        decoded = Cursor.decode(encoded)
        assert decoded.after == "abc123"
        assert decoded.limit == 20
    
    def test_decode_invalid(self):
        cursor = Cursor.decode("invalid")
        assert cursor.after is None
        assert cursor.before is None
        assert cursor.limit == 50


class TestCursorPaginator:
    """Test cursor paginator."""
    
    @pytest_asyncio.fixture
    async def test_data(self, db_session: AsyncSession):
        """Create test data."""
        import uuid
        from app.models.project import Project
        from app.models.organization import Organization
        
        org_id = f"test-org-{uuid.uuid4().hex[:8]}"
        org = Organization(
            id=org_id,
            name="Test Org",
            slug=f"test-org-{uuid.uuid4().hex[:8]}",
            industry="Technology",
            country="US",
            timezone="UTC",
            currency="USD",
        )
        db_session.add(org)
        await db_session.flush()
        
        projects = []
        base_time = datetime.now(timezone.utc)
        for i in range(15):
            p = Project(
                id=f"proj-{uuid.uuid4().hex[:8]}",
                organization_id=org_id,
                name=f"Project {i}",
                code=f"PRJ{i}",
                description=f"Project {i} description",
                status="active",
                progress=i * 5,
                updated_at=base_time - timedelta(days=i),  # Different updated_at for each
            )
            db_session.add(p)
            projects.append(p)
        
        await db_session.commit()
        return {"org_id": org_id, "projects": projects}
    
    async def test_paginate_projects_first_page(self, db_session: AsyncSession, test_data):
        """Test first page of projects."""
        page = await paginate_projects(
            db_session,
            organization_id=test_data["org_id"],
            limit=5,
        )
        
        assert len(page.items) == 5
        assert page.has_next is True
        assert page.next_cursor is not None
        assert page.prev_cursor is None
        
        # Items should be ordered by updated_at DESC
        for i in range(len(page.items) - 1):
            assert page.items[i].updated_at >= page.items[i + 1].updated_at
    
    async def test_paginate_projects_second_page(self, db_session: AsyncSession, test_data):
        """Test second page using cursor."""
        # Get first page
        page1 = await paginate_projects(
            db_session,
            organization_id=test_data["org_id"],
            limit=5,
        )
        
        # Get second page using cursor
        cursor = Cursor.decode(page1.next_cursor)
        page2 = await paginate_projects(
            db_session,
            organization_id=test_data["org_id"],
            cursor=cursor,
            limit=5,
        )
        
        assert len(page2.items) == 5
        assert page2.has_next is True
        assert page2.next_cursor is not None
        assert page2.prev_cursor is not None
        
        # No overlap between pages
        ids1 = {p.id for p in page1.items}
        ids2 = {p.id for p in page2.items}
        assert len(ids1 & ids2) == 0
    
    async def test_paginate_projects_with_status_filter(self, db_session: AsyncSession, test_data):
        """Test pagination with status filter."""
        # Update some projects to completed
        from app.models.project import Project
        await db_session.execute(
            Project.__table__.update()
            .where(Project.id.in_([p.id for p in test_data["projects"][:5]]))
            .values(status="completed")
        )
        await db_session.commit()
        
        # Filter by active status
        page = await paginate_projects(
            db_session,
            organization_id=test_data["org_id"],
            status="active",
            limit=10,
        )
        
        for p in page.items:
            assert p.status == "active"


class TestCursorEdgeCases:
    """Test edge cases for cursor pagination."""
    
    def test_empty_cursor(self):
        cursor = Cursor()
        assert cursor.after is None
        assert cursor.before is None
    
    def test_cursor_with_only_before(self):
        cursor = Cursor(before="abc123")
        encoded = cursor.encode()
        decoded = Cursor.decode(encoded)
        assert decoded.before == "abc123"
        assert decoded.after is None
    
    def test_cursor_limit(self):
        cursor = Cursor(after="abc", limit=100)
        encoded = cursor.encode()
        decoded = Cursor.decode(encoded)
        assert decoded.limit == 100


# Export for pytest
__all__ = [
    "TestCursor",
    "TestCursorPaginator",
    "TestCursorEdgeCases",
]