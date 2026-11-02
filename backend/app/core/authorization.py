"""
Advanced Authorization Engine with Cedar/OPA Integration.

Provides:
- Cedar policy language support for fine-grained ABAC/ReBAC
- OPA (Open Policy Agent) integration for Rego policies
- Policy management (CRUD, versioning, testing)
- Authorization decisions with context
- Policy simulation and testing
- Entity management (users, resources, groups)
- Schema validation
"""

import asyncio
import json
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Union
from uuid import uuid4

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)


class PolicyEngine(str, Enum):
    """Policy engine types."""
    CEDAR = "cedar"
    OPA = "opa"
    BOTH = "both"


class PolicyStatus(str, Enum):
    """Policy status."""
    DRAFT = "draft"
    ACTIVE = "active"
    DEPRECATED = "deprecated"
    ARCHIVED = "archived"


class Effect(str, Enum):
    """Policy effect."""
    ALLOW = "allow"
    DENY = "deny"


@dataclass
class Entity:
    """Entity for authorization (user, resource, group, role)."""
    id: str
    type: str  # User, Resource, Group, Role, Organization
    attributes: Dict[str, Any] = field(default_factory=dict)
    parents: List[str] = field(default_factory=list)  # Parent entity IDs
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Policy:
    """Authorization policy."""
    id: str
    name: str
    description: str
    engine: PolicyEngine
    content: str  # Cedar policy or Rego code
    status: PolicyStatus = PolicyStatus.DRAFT
    version: int = 1
    schema: Optional[Dict[str, Any]] = None
    tags: List[str] = field(default_factory=list)
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    activated_at: Optional[datetime] = None


@dataclass
class AuthorizationRequest:
    """Authorization request."""
    principal: Entity
    action: str
    resource: Entity
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AuthorizationDecision:
    """Authorization decision result."""
    allowed: bool
    effect: Effect
    policies_evaluated: List[str] = field(default_factory=list)
    matching_policies: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    evaluation_time_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PolicyTestCase:
    """Policy test case."""
    name: str
    request: AuthorizationRequest
    expected: bool
    description: str = ""


@dataclass
class PolicyTestResult:
    """Policy test result."""
    test_case: PolicyTestCase
    passed: bool
    decision: AuthorizationDecision
    error: Optional[str] = None


class CedarEngine:
    """Cedar policy engine wrapper."""

    def __init__(self, cedar_binary: str = "cedar"):
        self.cedar_binary = cedar_binary
        self._policies: Dict[str, Policy] = {}
        self._entities: Dict[str, Entity] = {}

    async def authorize(self, request: AuthorizationRequest, policies: List[Policy]) -> AuthorizationDecision:
        """Evaluate authorization request against Cedar policies."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            # Build Cedar request
            cedar_request = self._build_cedar_request(request)
            
            # Combine policies
            policy_text = "\n\n".join([p.content for p in policies if p.engine in (PolicyEngine.CEDAR, PolicyEngine.BOTH)])
            
            # Write to temp files
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cedar', delete=False) as pf:
                pf.write(policy_text)
                policy_file = pf.name
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as ef:
                json.dump(cedar_request, ef)
                entity_file = ef.name
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as rf:
                json.dump({
                    "principal": cedar_request["principal"],
                    "action": cedar_request["action"],
                    "resource": cedar_request["resource"],
                    "context": cedar_request["context"],
                }, rf)
                request_file = rf.name
            
            try:
                # Run Cedar CLI
                proc = await asyncio.create_subprocess_exec(
                    self.cedar_binary, "authorize",
                    "--policy", policy_file,
                    "--entities", entity_file,
                    "--request", request_file,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                
                result = json.loads(stdout.decode()) if stdout else {}
                
                allowed = result.get("decision") == "Allow"
                
                return AuthorizationDecision(
                    allowed=allowed,
                    effect=Effect.ALLOW if allowed else Effect.DENY,
                    policies_evaluated=[p.id for p in policies],
                    matching_policies=[p.id for p in policies if p.content in policy_text],
                    evaluation_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                )
            finally:
                os.unlink(policy_file)
                os.unlink(entity_file)
                os.unlink(request_file)
                
        except Exception as e:
            logger.error(f"Cedar evaluation error: {e}")
            return AuthorizationDecision(
                allowed=False,
                effect=Effect.DENY,
                errors=[str(e)],
                evaluation_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )

    def _build_cedar_request(self, request: AuthorizationRequest) -> Dict[str, Any]:
        """Build Cedar request format."""
        return {
            "principal": f"{request.principal.type}::{request.principal.id}",
            "action": f"Action::{request.action}",
            "resource": f"{request.resource.type}::{request.resource.id}",
            "context": request.context,
        }

    def validate_policy(self, policy_content: str) -> tuple[bool, List[str]]:
        """Validate Cedar policy syntax."""
        # In production, use Cedar CLI validate
        # For now, basic validation
        errors = []
        if not policy_content.strip():
            errors.append("Policy content is empty")
        if "permit" not in policy_content and "forbid" not in policy_content:
            errors.append("Policy must contain permit or forbid")
        return len(errors) == 0, errors


class OPAEngine:
    """OPA (Open Policy Agent) engine wrapper."""

    def __init__(self, opa_url: str = "http://localhost:8181"):
        self.opa_url = opa_url
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize HTTP session."""
        self._session = aiohttp.ClientSession()

    async def close(self):
        """Close HTTP session."""
        if self._session:
            await self._session.close()

    async def authorize(self, request: AuthorizationRequest, policies: List[Policy]) -> AuthorizationDecision:
        """Evaluate authorization request against OPA policies."""
        start_time = asyncio.get_event_loop().time()
        
        try:
            if not self._session:
                await self.initialize()
            
            # Build OPA input
            input_data = {
                "input": {
                    "principal": {
                        "type": request.principal.type,
                        "id": request.principal.id,
                        "attributes": request.principal.attributes,
                    },
                    "action": request.action,
                    "resource": {
                        "type": request.resource.type,
                        "id": request.resource.id,
                        "attributes": request.resource.attributes,
                    },
                    "context": request.context,
                }
            }
            
            # Query OPA
            async with self._session.post(
                f"{self.opa_url}/v1/data/authz/allow",
                json=input_data,
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    allowed = result.get("result", False)
                    return AuthorizationDecision(
                        allowed=allowed,
                        effect=Effect.ALLOW if allowed else Effect.DENY,
                        policies_evaluated=[p.id for p in policies],
                        evaluation_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                    )
                else:
                    error = await resp.text()
                    return AuthorizationDecision(
                        allowed=False,
                        effect=Effect.DENY,
                        errors=[f"OPA error: {error}"],
                        evaluation_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
                    )
        except Exception as e:
            logger.error(f"OPA evaluation error: {e}")
            return AuthorizationDecision(
                allowed=False,
                effect=Effect.DENY,
                errors=[str(e)],
                evaluation_time_ms=int((asyncio.get_event_loop().time() - start_time) * 1000),
            )

    async def load_policy(self, policy_id: str, policy_content: str) -> bool:
        """Load Rego policy into OPA."""
        try:
            if not self._session:
                await self.initialize()
            
            async with self._session.put(
                f"{self.opa_url}/v1/policies/{policy_id}",
                data=policy_content,
                headers={"Content-Type": "text/plain"},
            ) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            logger.error(f"Failed to load policy into OPA: {e}")
            return False


class AuthorizationEngine:
    """
    Unified Authorization Engine.

    Supports:
    - Cedar policies (AWS Cedar)
    - OPA/Rego policies
    - Hybrid evaluation
    - Policy management
    - Entity management
    - Testing and simulation
    """

    def __init__(
        self,
        default_engine: PolicyEngine = PolicyEngine.CEDAR,
        cedar_binary: str = "cedar",
        opa_url: str = "http://localhost:8181",
    ):
        self.default_engine = default_engine
        self.cedar_engine = CedarEngine(cedar_binary)
        self.opa_engine = OPAEngine(opa_url)
        self._policies: Dict[str, Policy] = {}
        self._entities: Dict[str, Entity] = {}
        self._policy_versions: Dict[str, List[Policy]] = {}

    async def initialize(self):
        """Initialize engines."""
        await self.opa_engine.initialize()
        logger.info("Authorization Engine initialized")

    async def close(self):
        """Close engines."""
        await self.opa_engine.close()

    # ==================== Policy Management ====================

    async def create_policy(
        self,
        name: str,
        content: str,
        engine: PolicyEngine,
        description: str = "",
        schema: Optional[Dict[str, Any]] = None,
        tags: List[str] = None,
        created_by: str = "",
    ) -> Policy:
        """Create a new policy."""
        policy = Policy(
            id=str(uuid4()),
            name=name,
            description=description,
            engine=engine,
            content=content,
            schema=schema,
            tags=tags or [],
            created_by=created_by,
        )

        # Validate
        if engine in (PolicyEngine.CEDAR, PolicyEngine.BOTH):
            valid, errors = self.cedar_engine.validate_policy(content)
            if not valid:
                raise ValueError(f"Invalid Cedar policy: {errors}")

        self._policies[policy.id] = policy
        if policy.id not in self._policy_versions:
            self._policy_versions[policy.id] = []
        self._policy_versions[policy.id].append(policy)

        # Load into OPA if needed
        if engine in (PolicyEngine.OPA, PolicyEngine.BOTH):
            await self.opa_engine.load_policy(policy.id, content)

        logger.info(f"Created policy: {policy.id} ({name})")
        return policy

    async def update_policy(
        self,
        policy_id: str,
        content: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[PolicyStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> Policy:
        """Update an existing policy."""
        if policy_id not in self._policies:
            raise ValueError(f"Policy not found: {policy_id}")

        policy = self._policies[policy_id]

        if content is not None:
            # Validate new content
            if policy.engine in (PolicyEngine.CEDAR, PolicyEngine.BOTH):
                valid, errors = self.cedar_engine.validate_policy(content)
                if not valid:
                    raise ValueError(f"Invalid Cedar policy: {errors}")
            
            policy.content = content
            policy.version += 1
            self._policy_versions[policy_id].append(policy)

        if description is not None:
            policy.description = description
        if status is not None:
            policy.status = status
            if status == PolicyStatus.ACTIVE:
                policy.activated_at = datetime.utcnow()
        if tags is not None:
            policy.tags = tags

        policy.updated_at = datetime.utcnow()

        # Reload into OPA
        if policy.engine in (PolicyEngine.OPA, PolicyEngine.BOTH):
            await self.opa_engine.load_policy(policy.id, policy.content)

        return policy

    async def delete_policy(self, policy_id: str) -> bool:
        """Delete a policy."""
        if policy_id not in self._policies:
            return False

        del self._policies[policy_id]
        # Keep versions for history
        return True

    async def get_policy(self, policy_id: str) -> Optional[Policy]:
        """Get policy by ID."""
        return self._policies.get(policy_id)

    async def list_policies(
        self,
        engine: Optional[PolicyEngine] = None,
        status: Optional[PolicyStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Policy]:
        """List policies with filters."""
        policies = list(self._policies.values())

        if engine:
            policies = [p for p in policies if p.engine == engine]
        if status:
            policies = [p for p in policies if p.status == status]
        if tags:
            policies = [p for p in policies if any(t in p.tags for t in tags)]

        return policies

    async def activate_policy(self, policy_id: str) -> Policy:
        """Activate a policy."""
        return await self.update_policy(policy_id, status=PolicyStatus.ACTIVE)

    async def deactivate_policy(self, policy_id: str) -> Policy:
        """Deactivate a policy."""
        return await self.update_policy(policy_id, status=PolicyStatus.DEPRECATED)

    def get_policy_versions(self, policy_id: str) -> List[Policy]:
        """Get all versions of a policy."""
        return self._policy_versions.get(policy_id, [])

    # ==================== Entity Management ====================

    async def create_entity(
        self,
        entity_type: str,
        entity_id: str,
        attributes: Dict[str, Any] = None,
        parents: List[str] = None,
    ) -> Entity:
        """Create an entity."""
        entity = Entity(
            id=entity_id,
            type=entity_type,
            attributes=attributes or {},
            parents=parents or [],
        )
        self._entities[f"{entity_type}::{entity_id}"] = entity
        return entity

    async def get_entity(self, entity_type: str, entity_id: str) -> Optional[Entity]:
        """Get entity by type and ID."""
        return self._entities.get(f"{entity_type}::{entity_id}")

    async def update_entity(
        self,
        entity_type: str,
        entity_id: str,
        attributes: Optional[Dict[str, Any]] = None,
        parents: Optional[List[str]] = None,
    ) -> Entity:
        """Update entity."""
        key = f"{entity_type}::{entity_id}"
        if key not in self._entities:
            raise ValueError(f"Entity not found: {key}")

        entity = self._entities[key]
        if attributes is not None:
            entity.attributes = attributes
        if parents is not None:
            entity.parents = parents
        entity.updated_at = datetime.utcnow()
        return entity

    async def delete_entity(self, entity_type: str, entity_id: str) -> bool:
        """Delete entity."""
        key = f"{entity_type}::{entity_id}"
        if key in self._entities:
            del self._entities[key]
            return True
        return False

    # ==================== Authorization ====================

    async def authorize(
        self,
        principal_type: str,
        principal_id: str,
        action: str,
        resource_type: str,
        resource_id: str,
        context: Dict[str, Any] = None,
        engine: Optional[PolicyEngine] = None,
    ) -> AuthorizationDecision:
        """Evaluate authorization request."""
        engine = engine or self.default_engine

        # Get entities
        principal = await self.get_entity(principal_type, principal_id)
        resource = await self.get_entity(resource_type, resource_id)

        if not principal:
            raise ValueError(f"Principal not found: {principal_type}::{principal_id}")
        if not resource:
            raise ValueError(f"Resource not found: {resource_type}::{resource_id}")

        request = AuthorizationRequest(
            principal=principal,
            action=action,
            resource=resource,
            context=context or {},
        )

        # Get active policies for engine
        policies = [
            p for p in self._policies.values()
            if p.status == PolicyStatus.ACTIVE and 
            (p.engine == engine or p.engine == PolicyEngine.BOTH)
        ]

        if engine == PolicyEngine.CEDAR:
            return await self.cedar_engine.authorize(request, policies)
        elif engine == PolicyEngine.OPA:
            return await self.opa_engine.authorize(request, policies)
        elif engine == PolicyEngine.BOTH:
            # Evaluate both, deny if either denies
            cedar_result = await self.cedar_engine.authorize(request, policies)
            opa_result = await self.opa_engine.authorize(request, policies)
            
            # Deny by default if either denies
            allowed = cedar_result.allowed and opa_result.allowed
            return AuthorizationDecision(
                allowed=allowed,
                effect=Effect.ALLOW if allowed else Effect.DENY,
                policies_evaluated=cedar_result.policies_evaluated + opa_result.policies_evaluated,
                errors=cedar_result.errors + opa_result.errors,
            )

        return AuthorizationDecision(
            allowed=False,
            effect=Effect.DENY,
            errors=[f"Unknown engine: {engine}"],
        )

    async def batch_authorize(
        self,
        requests: List[AuthorizationRequest],
        engine: Optional[PolicyEngine] = None,
    ) -> List[AuthorizationDecision]:
        """Evaluate multiple authorization requests."""
        return await asyncio.gather(*[
            self.authorize(
                r.principal.type, r.principal.id,
                r.action,
                r.resource.type, r.resource.id,
                r.context,
                engine,
            )
            for r in requests
        ])

    # ==================== Policy Testing ====================

    async def test_policy(
        self,
        policy_id: str,
        test_cases: List[PolicyTestCase],
    ) -> List[PolicyTestResult]:
        """Test a policy against test cases."""
        policy = await self.get_policy(policy_id)
        if not policy:
            raise ValueError(f"Policy not found: {policy_id}")

        results = []
        for test_case in test_cases:
            try:
                decision = await self.authorize(
                    test_case.request.principal.type,
                    test_case.request.principal.id,
                    test_case.request.action,
                    test_case.request.resource.type,
                    test_case.request.resource.id,
                    test_case.request.context,
                    policy.engine,
                )
                
                passed = decision.allowed == test_case.expected
                results.append(PolicyTestResult(
                    test_case=test_case,
                    passed=passed,
                    decision=decision,
                ))
            except Exception as e:
                results.append(PolicyTestResult(
                    test_case=test_case,
                    passed=False,
                    decision=AuthorizationDecision(
                        allowed=False,
                        effect=Effect.DENY,
                        errors=[str(e)],
                    ),
                    error=str(e),
                ))

        return results

    async def simulate(
        self,
        request: AuthorizationRequest,
        policies: List[Policy],
    ) -> Dict[str, AuthorizationDecision]:
        """Simulate authorization against multiple policy sets."""
        results = {}
        
        for policy in policies:
            decision = await self.authorize(
                request.principal.type,
                request.principal.id,
                request.action,
                request.resource.type,
                request.resource.id,
                request.context,
                policy.engine,
            )
            results[policy.id] = decision

        return results

    # ==================== Schema Management ====================

    def validate_schema(self, schema: Dict[str, Any]) -> tuple[bool, List[str]]:
        """Validate Cedar schema."""
        # Basic schema validation
        errors = []
        if "entityTypes" not in schema:
            errors.append("Schema must contain entityTypes")
        if "actions" not in schema:
            errors.append("Schema must contain actions")
        return len(errors) == 0, errors

    async def set_schema(self, schema: Dict[str, Any]) -> bool:
        """Set Cedar schema."""
        valid, errors = self.validate_schema(schema)
        if not valid:
            raise ValueError(f"Invalid schema: {errors}")
        
        # Store schema for validation
        self._schema = schema
        return True


# Global authorization engine instance
_auth_engine: Optional[AuthorizationEngine] = None


def get_auth_engine() -> AuthorizationEngine:
    """Get or create authorization engine singleton."""
    global _auth_engine
    if _auth_engine is None:
        _auth_engine = AuthorizationEngine()
    return _auth_engine


def init_auth_engine(
    default_engine: PolicyEngine = PolicyEngine.CEDAR,
    cedar_binary: str = "cedar",
    opa_url: str = "http://localhost:8181",
) -> AuthorizationEngine:
    """Initialize authorization engine."""
    global _auth_engine
    _auth_engine = AuthorizationEngine(
        default_engine=default_engine,
        cedar_binary=cedar_binary,
        opa_url=opa_url,
    )
    return _auth_engine