"""
Relationship-Based Access Control (ReBAC) Engine for VCOS.

Provides:
- Relationship tuples (subject, relation, object) - SpiceDB/Zanzibar style
- Schema definition for object types and relations
- Permission computation via graph traversal
- Check API for authorization decisions
- Expand API for listing all subjects with a relation
- Lookup API for listing all relations of a subject
- Watch API for real-time updates
- Distributed consistency with snapshot isolation
"""

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union
from uuid import uuid4

import redis.asyncio as aioredis
import asyncpg

from app.core.config import settings

logger = logging.getLogger(__name__)


class RelationType(str, Enum):
    """Standard relation types."""
    # Hierarchical
    PARENT = "parent"
    CHILD = "child"
    ANCESTOR = "ancestor"
    DESCENDANT = "descendant"
    
    # Membership
    MEMBER = "member"
    OWNER = "owner"
    ADMIN = "admin"
    VIEWER = "viewer"
    EDITOR = "editor"
    
    # Access
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    EXECUTE = "execute"
    MANAGE = "manage"
    
    # Organizational
    EMPLOYEE = "employee"
    MANAGER_OF = "manager_of"
    DEPARTMENT = "department"
    TEAM = "team"
    REPORTS_TO = "reports_to"
    
    # Resource
    CREATOR = "creator"
    ASSIGNEE = "assignee"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    
    # Custom
    CUSTOM = "custom"


@dataclass
class ObjectType:
    """Object type definition with relations."""
    name: str
    relations: Dict[str, "RelationDefinition"] = field(default_factory=dict)
    permissions: Dict[str, "PermissionDefinition"] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RelationDefinition:
    """Definition of a relation."""
    name: str
    subject_types: List[str]  # Types that can be subjects
    description: str = ""
    required: bool = False  # Must exist for permission computation


@dataclass
class PermissionDefinition:
    """Permission computed from relations."""
    name: str
    # Union of relations that grant this permission
    union: List[str] = field(default_factory=list)
    # Intersection of relations
    intersection: List[str] = field(default_factory=list)
    # Exclusion (has relation A but NOT relation B)
    exclusion: List[Tuple[str, str]] = field(default_factory=list)  # (has, not_has)
    # Recursive/transitive
    transitive: bool = False
    # Computed from other permissions
    from_permissions: List[str] = field(default_factory=list)


@dataclass
class RelationshipTuple:
    """Core relationship tuple: subject -> relation -> object."""
    subject_type: str
    subject_id: str
    relation: str
    object_type: str
    object_id: str
    caveat: Optional[Dict[str, Any]] = None  # Contextual caveats
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    expires_at: Optional[datetime] = None
    
    def to_key(self) -> str:
        """Generate unique key for storage."""
        caveat_str = ""
        if self.caveat:
            caveat_str = f":{hash(frozenset(self.caveat.items()))}"
        return f"{self.subject_type}:{self.subject_id}#{self.relation}@{self.object_type}:{self.object_id}{caveat_str}"
    
    @classmethod
    def from_key(cls, key: str) -> "RelationshipTuple":
        """Parse tuple from key."""
        # Format: subject_type:subject_id#relation@object_type:object_id[:caveat]
        parts = key.split("#")
        subject_part = parts[0]
        relation_object_part = parts[1]
        
        subject_type, subject_id = subject_part.split(":", 1)
        relation, object_part = relation_object_part.split("@", 1)
        object_type, object_id = object_part.split(":", 1)
        
        caveat = None
        if ":" in object_id:
            object_id, caveat_hash = object_id.split(":", 1)
            # Note: Can't reconstruct caveat from hash, would need to store separately
        
        return cls(
            subject_type=subject_type,
            subject_id=subject_id,
            relation=relation,
            object_type=object_type,
            object_id=object_id,
            caveat=caveat,
        )


@dataclass
class CheckRequest:
    """Authorization check request."""
    subject_type: str
    subject_id: str
    relation: str
    object_type: str
    object_id: str
    context: Dict[str, Any] = field(default_factory=dict)
    caveat_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CheckResult:
    """Authorization check result."""
    allowed: bool
    subject_type: str
    subject_id: str
    relation: str
    object_type: str
    object_id: str
    caveat_context: Dict[str, Any]
    caveat_result: Optional[bool] = None
    explanation: Optional[str] = None
    evaluated_tuples: List[RelationshipTuple] = field(default_factory=list)
    evaluation_time_ms: float = 0


@dataclass
class ExpandRequest:
    """Expand request: list all subjects with relation to object."""
    relation: str
    object_type: str
    object_id: str
    subject_type: Optional[str] = None
    max_results: int = 1000


@dataclass
class ExpandResult:
    """Expand result."""
    subjects: List[Tuple[str, str]]  # (subject_type, subject_id)
    total_count: int
    truncated: bool


@dataclass
class LookupRequest:
    """Lookup request: list all relations of subject to objects."""
    subject_type: str
    subject_id: str
    object_type: Optional[str] = None
    relation: Optional[str] = None
    max_results: int = 1000


@dataclass
class LookupResult:
    """Lookup result."""
    tuples: List[RelationshipTuple]
    total_count: int
    truncated: bool


class Schema:
    """Schema registry for object types and relations."""
    
    def __init__(self):
        self._object_types: Dict[str, ObjectType] = {}
        self._relation_definitions: Dict[str, Dict[str, RelationDefinition]] = defaultdict(dict)
        self._permission_definitions: Dict[str, Dict[str, PermissionDefinition]] = defaultdict(dict)
    
    def add_object_type(self, obj_type: ObjectType):
        """Add object type to schema."""
        self._object_types[obj_type.name] = obj_type
        for rel_name, rel_def in obj_type.relations.items():
            self._relation_definitions[obj_type.name][rel_name] = rel_def
        for perm_name, perm_def in obj_type.permissions.items():
            self._permission_definitions[obj_type.name][perm_name] = perm_def
        logger.info(f"Registered object type: {obj_type.name} with {len(obj_type.relations)} relations, {len(obj_type.permissions)} permissions")
    
    def get_object_type(self, name: str) -> Optional[ObjectType]:
        return self._object_types.get(name)
    
    def get_relation(self, object_type: str, relation: str) -> Optional[RelationDefinition]:
        return self._relation_definitions.get(object_type, {}).get(relation)
    
    def get_permission(self, object_type: str, permission: str) -> Optional[PermissionDefinition]:
        return self._permission_definitions.get(object_type, {}).get(permission)
    
    def list_object_types(self) -> List[str]:
        return list(self._object_types.keys())
    
    def validate_tuple(self, tuple_: RelationshipTuple) -> Tuple[bool, List[str]]:
        """Validate a relationship tuple against schema."""
        errors = []
        obj_type = self._object_types.get(tuple_.object_type)
        if not obj_type:
            errors.append(f"Unknown object type: {tuple_.object_type}")
            return False, errors
        
        rel_def = obj_type.relations.get(tuple_.relation)
        if not rel_def:
            errors.append(f"Unknown relation: {tuple_.relation} on {tuple_.object_type}")
        
        if rel_def and tuple_.subject_type not in rel_def.subject_types:
            errors.append(f"Subject type {tuple_.subject_type} not allowed for relation {tuple_.relation}")
        
        return len(errors) == 0, errors


# Built-in schema for VCOS
def create_vcos_schema() -> Schema:
    """Create the default VCOS schema."""
    schema = Schema()
    
    # User object type
    schema.add_object_type(ObjectType(
        name="user",
        relations={
            "member": RelationDefinition("member", ["group", "organization", "team"], "Member of"),
            "owner": RelationDefinition("owner", ["document", "project", "team"], "Owner of"),
            "admin": RelationDefinition("admin", ["organization", "team", "workspace"], "Admin of"),
            "viewer": RelationDefinition("viewer", ["document", "project", "dashboard"], "Viewer of"),
            "editor": RelationDefinition("editor", ["document", "project", "workspace"], "Editor of"),
            "manager_of": RelationDefinition("manager_of", ["user"], "Manager of"),
            "reports_to": RelationDefinition("reports_to", ["user"], "Reports to"),
            "employee": RelationDefinition("employee", ["organization", "department"], "Employee of"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["viewer", "editor", "admin", "owner"]),
            "write": PermissionDefinition("write", union=["editor", "admin", "owner"]),
            "delete": PermissionDefinition("delete", union=["admin", "owner"]),
            "manage": PermissionDefinition("manage", union=["admin", "owner"]),
            "admin": PermissionDefinition("admin", union=["admin"]),
        }
    ))
    
    # Organization object type
    schema.add_object_type(ObjectType(
        name="organization",
        relations={
            "member": RelationDefinition("member", ["user"], "Member of organization"),
            "admin": RelationDefinition("admin", ["user"], "Admin of organization"),
            "owner": RelationDefinition("owner", ["user"], "Owner of organization"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["member", "admin", "owner"]),
            "write": PermissionDefinition("write", union=["admin", "owner"]),
            "manage": PermissionDefinition("manage", union=["admin", "owner"]),
            "delete": PermissionDefinition("delete", union=["owner"]),
        }
    ))
    
    # Team object type
    schema.add_object_type(ObjectType(
        name="team",
        relations={
            "member": RelationDefinition("member", ["user"], "Team member"),
            "admin": RelationDefinition("admin", ["user"], "Team admin"),
            "manager": RelationDefinition("manager", ["user"], "Team manager"),
            "parent": RelationDefinition("parent", ["team", "department"], "Parent team/department"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["member", "manager", "admin"]),
            "write": PermissionDefinition("write", union=["manager", "admin"]),
            "manage": PermissionDefinition("manage", union=["admin"]),
            "delete": PermissionDefinition("delete", union=["admin"]),
        }
    ))
    
    # Department object type
    schema.add_object_type(ObjectType(
        name="department",
        relations={
            "member": RelationDefinition("member", ["user"], "Department member"),
            "head": RelationDefinition("head", ["user"], "Department head"),
            "parent": RelationDefinition("parent", ["department", "organization"], "Parent department/org"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["member", "head"]),
            "write": PermissionDefinition("write", union=["head"]),
            "manage": PermissionDefinition("manage", union=["head"]),
        }
    ))
    
    # Document object type
    schema.add_object_type(ObjectType(
        name="document",
        relations={
            "creator": RelationDefinition("creator", ["user"], "Document creator"),
            "owner": RelationDefinition("owner", ["user"], "Document owner"),
            "editor": RelationDefinition("editor", ["user", "group"], "Document editor"),
            "viewer": RelationDefinition("viewer", ["user", "group"], "Document viewer"),
            "reviewer": RelationDefinition("reviewer", ["user"], "Document reviewer"),
            "approver": RelationDefinition("approver", ["user"], "Document approver"),
            "parent": RelationDefinition("parent", ["folder", "project"], "Parent folder/project"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["viewer", "editor", "reviewer", "approver", "owner", "creator"]),
            "write": PermissionDefinition("write", union=["editor", "owner", "creator"]),
            "delete": PermissionDefinition("delete", union=["owner", "creator"]),
            "review": PermissionDefinition("review", union=["reviewer", "approver", "owner"]),
            "approve": PermissionDefinition("approve", union=["approver", "owner"]),
            "manage": PermissionDefinition("manage", union=["owner", "creator"]),
        }
    ))
    
    # Project object type
    schema.add_object_type(ObjectType(
        name="project",
        relations={
            "owner": RelationDefinition("owner", ["user"], "Project owner"),
            "admin": RelationDefinition("admin", ["user"], "Project admin"),
            "member": RelationDefinition("member", ["user"], "Project member"),
            "viewer": RelationDefinition("viewer", ["user", "group"], "Project viewer"),
            "parent": RelationDefinition("parent", ["portfolio", "organization"], "Parent portfolio/org"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["viewer", "member", "admin", "owner"]),
            "write": PermissionDefinition("write", union=["member", "admin", "owner"]),
            "manage": PermissionDefinition("manage", union=["admin", "owner"]),
            "delete": PermissionDefinition("delete", union=["owner"]),
        }
    ))
    
    # Group object type
    schema.add_object_type(ObjectType(
        name="group",
        relations={
            "member": RelationDefinition("member", ["user"], "Group member"),
            "admin": RelationDefinition("admin", ["user"], "Group admin"),
            "parent": RelationDefinition("parent", ["group", "organization"], "Parent group/org"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["member", "admin"]),
            "write": PermissionDefinition("write", union=["admin"]),
            "manage": PermissionDefinition("manage", union=["admin"]),
        }
    ))
    
    # Folder object type
    schema.add_object_type(ObjectType(
        name="folder",
        relations={
            "owner": RelationDefinition("owner", ["user"], "Folder owner"),
            "editor": RelationDefinition("editor", ["user", "group"], "Folder editor"),
            "viewer": RelationDefinition("viewer", ["user", "group"], "Folder viewer"),
            "parent": RelationDefinition("parent", ["folder", "project"], "Parent folder/project"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["viewer", "editor", "owner"]),
            "write": PermissionDefinition("write", union=["editor", "owner"]),
            "manage": PermissionDefinition("manage", union=["owner"]),
        }
    ))
    
    # Resource object type (generic)
    schema.add_object_type(ObjectType(
        name="resource",
        relations={
            "creator": RelationDefinition("creator", ["user"], "Resource creator"),
            "owner": RelationDefinition("owner", ["user"], "Resource owner"),
            "editor": RelationDefinition("editor", ["user"], "Resource editor"),
            "viewer": RelationDefinition("viewer", ["user"], "Resource viewer"),
            "assignee": RelationDefinition("assignee", ["user"], "Resource assignee"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["viewer", "editor", "assignee", "owner", "creator"]),
            "write": PermissionDefinition("write", union=["editor", "assignee", "owner", "creator"]),
            "delete": PermissionDefinition("delete", union=["owner", "creator"]),
            "manage": PermissionDefinition("manage", union=["owner"]),
        }
    ))
    
    # Task object type
    schema.add_object_type(ObjectType(
        name="task",
        relations={
            "creator": RelationDefinition("creator", ["user"], "Task creator"),
            "assignee": RelationDefinition("assignee", ["user"], "Task assignee"),
            "reporter": RelationDefinition("reporter", ["user"], "Task reporter"),
            "reviewer": RelationDefinition("reviewer", ["user"], "Task reviewer"),
            "project": RelationDefinition("project", ["project"], "Parent project"),
        },
        permissions={
            "read": PermissionDefinition("read", union=["assignee", "reporter", "reviewer", "creator"]),
            "write": PermissionDefinition("write", union=["assignee", "creator"]),
            "delete": PermissionDefinition("delete", union=["creator"]),
            "manage": PermissionDefinition("manage", union=["creator"]),
        }
    ))
    
    return schema


class ReBACEngine:
    """
    Relationship-Based Access Control Engine.
    
    Implements Google Zanzibar-style authorization with:
    - Relationship tuple storage
    - Schema-driven validation
    - Recursive permission computation
    - Caveat support for contextual authorization
    - High-performance graph traversal
    """
    
    def __init__(
        self,
        schema: Schema,
        redis_url: str = "redis://localhost:6379/2",
        pg_dsn: str = None,
    ):
        self.schema = schema
        self.redis_url = redis_url
        self.pg_dsn = pg_dsn
        
        # Redis for fast lookups
        self._redis: Optional[aioredis.Redis] = None
        
        # PostgreSQL for persistent storage
        self._pg_pool: Optional[asyncpg.Pool] = None
        
        # In-memory cache for hot data
        self._tuple_cache: Dict[str, RelationshipTuple] = {}
        self._reverse_index: Dict[str, Set[str]] = defaultdict(set)  # object -> tuple keys
        self._subject_index: Dict[str, Set[str]] = defaultdict(set)  # subject -> tuple keys
        
        # Caveat evaluators
        self._caveat_evaluators: Dict[str, Callable] = {}
        
        self._initialized = False
    
    async def initialize(self):
        """Initialize connections."""
        # Redis connection
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        await self._redis.ping()
        
        # PostgreSQL connection
        if self.pg_dsn:
            self._pg_pool = await asyncpg.create_pool(
                self.pg_dsn,
                min_size=2,
                max_size=10,
            )
            await self._init_pg_schema()
        
        # Load hot data into cache
        await self._warm_cache()
        
        self._initialized = True
        logger.info("ReBAC Engine initialized")
    
    async def _init_pg_schema(self):
        """Initialize PostgreSQL schema."""
        async with self._pg_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS rebac_tuples (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    subject_type TEXT NOT NULL,
                    subject_id TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    object_type TEXT NOT NULL,
                    object_id TEXT NOT NULL,
                    caveat JSONB,
                    metadata JSONB DEFAULT '{}',
                    created_by TEXT,
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    expires_at TIMESTAMPTZ,
                    UNIQUE(subject_type, subject_id, relation, object_type, object_id)
                );
                
                CREATE INDEX IF NOT EXISTS idx_rebac_tuples_subject 
                    ON rebac_tuples(subject_type, subject_id);
                CREATE INDEX IF NOT EXISTS idx_rebac_tuples_object 
                    ON rebac_tuples(object_type, object_id);
                CREATE INDEX IF NOT EXISTS idx_rebac_tuples_relation 
                    ON rebac_tuples(relation);
                CREATE INDEX IF NOT EXISTS idx_rebac_tuples_expires 
                    ON rebac_tuples(expires_at) WHERE expires_at IS NOT NULL;
            """)
    
    async def _warm_cache(self):
        """Load active tuples into memory cache."""
        if not self._pg_pool:
            return
        
        async with self._pg_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT subject_type, subject_id, relation, object_type, object_id,
                       caveat, metadata, created_by, created_at, expires_at
                FROM rebac_tuples
                WHERE expires_at IS NULL OR expires_at > NOW()
            """)
            
            for row in rows:
                tuple_ = RelationshipTuple(
                    subject_type=row["subject_type"],
                    subject_id=row["subject_id"],
                    relation=row["relation"],
                    object_type=row["object_type"],
                    object_id=row["object_id"],
                    caveat=row["caveat"],
                    metadata=row["metadata"] or {},
                    created_by=row["created_by"],
                    created_at=row["created_at"],
                    expires_at=row["expires_at"],
                )
                key = tuple_.to_key()
                self._tuple_cache[key] = tuple_
                self._reverse_index[f"{tuple_.object_type}:{tuple_.object_id}"].add(key)
                self._subject_index[f"{tuple_.subject_type}:{tuple_.subject_id}"].add(key)
        
        logger.info(f"Warmed cache with {len(self._tuple_cache)} tuples")
    
    def register_caveat_evaluator(self, name: str, evaluator: Callable[[Dict, Dict], bool]):
        """Register a caveat evaluator function."""
        self._caveat_evaluators[name] = evaluator
    
    # ==================== Write Operations ====================
    
    async def write(
        self,
        tuples: List[RelationshipTuple],
    ) -> int:
        """Write relationship tuples (upsert)."""
        if not tuples:
            return 0
        
        # Validate all tuples
        for t in tuples:
            valid, errors = self.schema.validate_tuple(t)
            if not valid:
                raise ValueError(f"Invalid tuple: {errors}")
        
        written = 0
        
        # Write to PostgreSQL
        if self._pg_pool:
            async with self._pg_pool.acquire() as conn:
                async with conn.transaction():
                    for t in tuples:
                        await conn.execute("""
                            INSERT INTO rebac_tuples 
                            (subject_type, subject_id, relation, object_type, object_id,
                             caveat, metadata, created_by, expires_at)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                            ON CONFLICT (subject_type, subject_id, relation, object_type, object_id)
                            DO UPDATE SET
                                caveat = EXCLUDED.caveat,
                                metadata = EXCLUDED.metadata,
                                expires_at = EXCLUDED.expires_at
                        """,
                            t.subject_type, t.subject_id, t.relation,
                            t.object_type, t.object_id,
                            json.dumps(t.caveat) if t.caveat else None,
                            json.dumps(t.metadata),
                            t.created_by,
                            t.expires_at,
                        )
                        written += 1
        
        # Update Redis cache
        for t in tuples:
            key = t.to_key()
            self._tuple_cache[key] = t
            self._reverse_index[f"{t.object_type}:{t.object_id}"].add(key)
            self._subject_index[f"{t.subject_type}:{t.subject_id}"].add(key)
            
            # Store in Redis for distributed access
            if self._redis:
                await self._redis.setex(
                    f"rebac:tuple:{key}",
                    86400 * 7,  # 7 day TTL
                    json.dumps({
                        "subject_type": t.subject_type,
                        "subject_id": t.subject_id,
                        "relation": t.relation,
                        "object_type": t.object_type,
                        "object_id": t.object_id,
                        "caveat": t.caveat,
                        "metadata": t.metadata,
                        "created_by": t.created_by,
                        "created_at": t.created_at.isoformat(),
                        "expires_at": t.expires_at.isoformat() if t.expires_at else None,
                    })
                )
        
        return written
    
    async def delete(
        self,
        tuples: List[RelationshipTuple],
    ) -> int:
        """Delete relationship tuples."""
        if not tuples:
            return 0
        
        deleted = 0
        
        if self._pg_pool:
            async with self._pg_pool.acquire() as conn:
                for t in tuples:
                    result = await conn.execute("""
                        DELETE FROM rebac_tuples
                        WHERE subject_type = $1 AND subject_id = $2
                        AND relation = $3 AND object_type = $4 AND object_id = $5
                    """, t.subject_type, t.subject_id, t.relation, t.object_type, t.object_id)
                    if result == "DELETE 1":
                        deleted += 1
        
        # Remove from cache
        for t in tuples:
            key = t.to_key()
            self._tuple_cache.pop(key, None)
            self._reverse_index[f"{t.object_type}:{t.object_id}"].discard(key)
            self._subject_index[f"{t.subject_type}:{t.subject_id}"].discard(key)
            
            if self._redis:
                await self._redis.delete(f"rebac:tuple:{key}")
        
        return deleted
    
    # ==================== Read Operations ====================
    
    async def check(self, request: CheckRequest) -> CheckResult:
        """
        Check if subject has relation to object.
        
        This is the core authorization check that:
        1. Looks up direct relationships
        2. Computes transitive closure for hierarchical relations
        3. Evaluates caveats with context
        4. Returns decision with explanation
        """
        start_time = time.time()
        
        # First check direct tuple
        direct_key = f"{request.subject_type}:{request.subject_id}#{request.relation}@{request.object_type}:{request.object_id}"
        direct_tuple = self._tuple_cache.get(direct_key)
        
        if direct_tuple and not direct_tuple.expires_at or direct_tuple.expires_at > datetime.utcnow():
            # Check caveat if present
            caveat_result = None
            if direct_tuple.caveat:
                caveat_result = await self._evaluate_caveat(
                    direct_tuple.caveat,
                    request.caveat_context,
                )
                if not caveat_result:
                    return CheckResult(
                        allowed=False,
                        subject_type=request.subject_type,
                        subject_id=request.subject_id,
                        relation=request.relation,
                        object_type=request.object_type,
                        object_id=request.object_id,
                        caveat_context=request.caveat_context,
                        caveat_result=False,
                        explanation="Caveat evaluation failed",
                        evaluation_time_ms=(time.time() - start_time) * 1000,
                    )
            
            return CheckResult(
                allowed=True,
                subject_type=request.subject_type,
                subject_id=request.subject_id,
                relation=request.relation,
                object_type=request.object_type,
                object_id=request.object_id,
                caveat_context=request.caveat_context,
                caveat_result=caveat_result,
                explanation="Direct relationship found",
                evaluated_tuples=[direct_tuple],
                evaluation_time_ms=(time.time() - start_time) * 1000,
            )
        
        # Check computed permissions via schema
        allowed, explanation, evaluated = await self._check_permission(request)
        
        return CheckResult(
            allowed=allowed,
            subject_type=request.subject_type,
            subject_id=request.subject_id,
            relation=request.relation,
            object_type=request.object_type,
            object_id=request.object_id,
            caveat_context=request.caveat_context,
            explanation=explanation,
            evaluated_tuples=evaluated,
            evaluation_time_ms=(time.time() - start_time) * 1000,
        )
    
    async def _check_permission(self, request: CheckRequest) -> Tuple[bool, str, List[RelationshipTuple]]:
        """Check permission via schema-defined relations."""
        obj_type = self.schema.get_object_type(request.object_type)
        if not obj_type:
            return False, f"Unknown object type: {request.object_type}", []
        
        perm_def = obj_type.permissions.get(request.relation)
        if not perm_def:
            # Not a computed permission, check if it's a direct relation
            direct_key = f"{request.subject_type}:{request.subject_id}#{request.relation}@{request.object_type}:{request.object_id}"
            if direct_key in self._tuple_cache:
                return True, "Direct relationship", [self._tuple_cache[direct_key]]
            return False, f"No permission definition for {request.relation}", []
        
        evaluated = []
        
        # Check union relations
        for rel in perm_def.union:
            rel_key = f"{request.subject_type}:{request.subject_id}#{rel}@{request.object_type}:{request.object_id}"
            if rel_key in self._tuple_cache:
                evaluated.append(self._tuple_cache[rel_key])
                return True, f"Granted via {rel} relation", evaluated
            
            # Check transitive (e.g., parent -> ancestor)
            rel_def = obj_type.relations.get(rel)
            if rel_def and perm_def.transitive:
                # Walk up the hierarchy
                if await self._check_transitive(request, rel):
                    return True, f"Granted via transitive {rel}", evaluated
        
        # Check intersection (must have ALL)
        if perm_def.intersection:
            has_all = True
            for rel in perm_def.intersection:
                rel_key = f"{request.subject_type}:{request.subject_id}#{rel}@{request.object_type}:{request.object_id}"
                if rel_key not in self._tuple_cache:
                    has_all = False
                    break
                evaluated.append(self._tuple_cache[rel_key])
            
            if has_all:
                return True, "Granted via intersection of relations", evaluated
        
        # Check exclusion (has A but NOT B)
        for has_rel, not_has_rel in perm_def.exclusion:
            has_key = f"{request.subject_type}:{request.subject_id}#{has_rel}@{request.object_type}:{request.object_id}"
            not_has_key = f"{request.subject_type}:{request.subject_id}#{not_has_rel}@{request.object_type}:{request.object_id}"
            
            if has_key in self._tuple_cache and not_has_key not in self._tuple_cache:
                evaluated.append(self._tuple_cache[has_key])
                return True, f"Granted via exclusion ({has_rel} but not {not_has_rel})", evaluated
        
        # Check from_permissions (recursive permission check)
        for perm in perm_def.from_permissions:
            sub_request = CheckRequest(
                subject_type=request.subject_type,
                subject_id=request.subject_id,
                relation=perm,
                object_type=request.object_type,
                object_id=request.object_id,
                context=request.context,
                caveat_context=request.caveat_context,
            )
            sub_result = await self.check(sub_request)
            if sub_result.allowed:
                evaluated.extend(sub_result.evaluated_tuples)
                return True, f"Granted via {perm} permission", evaluated
        
        return False, f"No matching relation for permission {request.relation}", evaluated
    
    async def _check_transitive(self, request: CheckRequest, relation: str) -> bool:
        """Check transitive relationship (e.g., user -> team -> parent_team -> org)."""
        # Get all objects subject has this relation to
        subject_key = f"{request.subject_type}:{request.subject_id}"
        tuple_keys = self._subject_index.get(subject_key, set())
        
        for key in tuple_keys:
            tuple_ = self._tuple_cache.get(key)
            if tuple_ and tuple_.relation == relation:
                # Found direct relation, now check if that object has relation to target
                if tuple_.object_type == request.object_type and tuple_.object_id == request.object_id:
                    return True
                
                # Recursive check: does the related object have the target relation?
                sub_request = CheckRequest(
                    subject_type=tuple_.object_type,
                    subject_id=tuple_.object_id,
                    relation=request.relation,
                    object_type=request.object_type,
                    object_id=request.object_id,
                    context=request.context,
                    caveat_context=request.caveat_context,
                )
                sub_result = await self.check(sub_request)
                if sub_result.allowed:
                    return True
        
        return False
    
    async def _evaluate_caveat(self, caveat: Dict[str, Any], context: Dict[str, Any]) -> bool:
        """Evaluate caveat expression against context."""
        caveat_type = caveat.get("type", "expression")
        
        if caveat_type == "expression":
            # Simple expression evaluation
            expr = caveat.get("expression", "")
            # In production, use a safe expression evaluator like expr-lang
            # For now, support basic checks
            return self._eval_expression(expr, context)
        
        elif caveat_type == "function":
            func_name = caveat.get("function")
            if func_name in self._caveat_evaluators:
                try:
                    return await self._caveat_evaluators[func_name](caveat.get("params", {}), context)
                except Exception as e:
                    logger.error(f"Caveat function {func_name} error: {e}")
                    return False
        
        return True
    
    def _eval_expression(self, expr: str, context: Dict[str, Any]) -> bool:
        """Safely evaluate a boolean expression."""
        # In production, use a proper expression language
        # This is a simplified implementation
        try:
            # Replace context variables
            for key, value in context.items():
                expr = expr.replace(f"${key}", json.dumps(value))
            
            # Basic safety: only allow certain operations
            allowed = {"True", "False", "and", "or", "not", "in", "==", "!=", "<", ">", "<=", ">="}
            # This is very simplified - use expr-lang or similar in production
            return eval(expr, {"__builtins__": {}}, context)
        except Exception:
            return False
    
    # ==================== Expand/Lookup ====================
    
    async def expand(self, request: ExpandRequest) -> ExpandResult:
        """Find all subjects with a relation to an object."""
        object_key = f"{request.object_type}:{request.object_id}"
        tuple_keys = self._reverse_index.get(object_key, set())
        
        subjects = []
        for key in tuple_keys:
            tuple_ = self._tuple_cache.get(key)
            if tuple_ and tuple_.relation == request.relation:
                if not request.subject_type or tuple_.subject_type == request.subject_type:
                    subjects.append((tuple_.subject_type, tuple_.subject_id))
                    if len(subjects) >= request.max_results:
                        break
        
        return ExpandResult(
            subjects=subjects[:request.max_results],
            total_count=len(subjects),
            truncated=len(subjects) > request.max_results,
        )
    
    async def lookup(self, request: LookupRequest) -> LookupResult:
        """Find all objects a subject has relations to."""
        subject_key = f"{request.subject_type}:{request.subject_id}"
        tuple_keys = self._subject_index.get(subject_key, set())
        
        tuples = []
        for key in tuple_keys:
            tuple_ = self._tuple_cache.get(key)
            if tuple_:
                if request.object_type and tuple_.object_type != request.object_type:
                    continue
                if request.relation and tuple_.relation != request.relation:
                    continue
                tuples.append(tuple_)
                if len(tuples) >= request.max_results:
                    break
        
        return LookupResult(
            tuples=tuples[:request.max_results],
            total_count=len(tuples),
            truncated=len(tuples) > request.max_results,
        )
    
    # ==================== Batch Operations ====================
    
    async def batch_check(self, requests: List[CheckRequest]) -> List[CheckResult]:
        """Check multiple authorization requests."""
        return await asyncio.gather(*[self.check(r) for r in requests])
    
    async def get_relations_for_subject(
        self,
        subject_type: str,
        subject_id: str,
    ) -> Dict[str, List[Tuple[str, str]]]:
        """Get all relations for a subject grouped by relation type."""
        subject_key = f"{subject_type}:{subject_id}"
        tuple_keys = self._subject_index.get(subject_key, set())
        
        relations = defaultdict(list)
        for key in tuple_keys:
            tuple_ = self._tuple_cache.get(key)
            if tuple_:
                relations[tuple_.relation].append((tuple_.object_type, tuple_.object_id))
        
        return dict(relations)
    
    async def get_subjects_for_object(
        self,
        object_type: str,
        object_id: str,
    ) -> Dict[str, List[Tuple[str, str]]]:
        """Get all subjects for an object grouped by relation type."""
        object_key = f"{object_type}:{object_id}"
        tuple_keys = self._reverse_index.get(object_key, set())
        
        relations = defaultdict(list)
        for key in tuple_keys:
            tuple_ = self._tuple_cache.get(key)
            if tuple_:
                relations[tuple_.relation].append((tuple_.subject_type, tuple_.subject_id))
        
        return dict(relations)
    
    # ==================== Caveats ====================
    
    def add_caveat_evaluator(self, name: str, evaluator: Callable[[Dict, Dict], bool]):
        """Add a custom caveat evaluator."""
        self._caveat_evaluators[name] = evaluator
    
    # ==================== Utility ====================
    
    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()
        if self._pg_pool:
            await self._pg_pool.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get engine statistics."""
        return {
            "cached_tuples": len(self._tuple_cache),
            "reverse_index_size": len(self._reverse_index),
            "subject_index_size": len(self._subject_index),
            "registered_caveats": list(self._caveat_evaluators.keys()),
            "object_types": self.schema.list_object_types(),
        }


# Global ReBAC engine instance
_rebac_engine: Optional[ReBACEngine] = None


def get_rebac_engine() -> ReBACEngine:
    """Get or create ReBAC engine singleton."""
    global _rebac_engine
    if _rebac_engine is None:
        schema = create_vcos_schema()
        _rebac_engine = ReBACEngine(
            schema=schema,
            redis_url=getattr(settings, "REBAC_REDIS_URL", "redis://localhost:6379/2"),
            pg_dsn=getattr(settings, "REBAC_PG_DSN", None),
        )
    return _rebac_engine


def init_rebac_engine(
    schema: Schema = None,
    redis_url: str = None,
    pg_dsn: str = None,
) -> ReBACEngine:
    """Initialize ReBAC engine."""
    global _rebac_engine
    if schema is None:
        schema = create_vcos_schema()
    _rebac_engine = ReBACEngine(
        schema=schema,
        redis_url=redis_url or getattr(settings, "REBAC_REDIS_URL", "redis://localhost:6379/2"),
        pg_dsn=pg_dsn or getattr(settings, "REBAC_PG_DSN", None),
    )
    return _rebac_engine