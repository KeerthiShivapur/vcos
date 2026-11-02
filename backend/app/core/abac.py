from typing import Dict, List, Optional, Set, Any
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import hashlib
import json


class Action(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    EXECUTE = "execute"
    APPROVE = "approve"
    REJECT = "reject"


class ResourceType(str, Enum):
    ORGANIZATION = "organization"
    USER = "user"
    TEAM = "team"
    PROJECT = "project"
    TASK = "task"
    DOCUMENT = "document"
    WORKFLOW = "workflow"
    PIPELINE = "pipeline"
    BLOCKER = "blocker"
    DECISION = "decision"
    ROLE = "role"
    PERMISSION = "permission"
    INTEGRATION = "integration"
    REPORT = "report"
    SETTINGS = "settings"
    AUDIT_LOG = "audit_log"


@dataclass
class Attribute:
    key: str
    value: Any
    attribute_type: str = "string"


@dataclass
class Subject:
    id: str
    type: str
    attributes: Dict[str, Attribute] = field(default_factory=dict)
    
    def get_attribute(self, key: str) -> Optional[Any]:
        attr = self.attributes.get(key)
        return attr.value if attr else None


@dataclass
class Resource:
    id: str
    type: ResourceType
    attributes: Dict[str, Attribute] = field(default_factory=dict)
    owner_id: Optional[str] = None
    organization_id: Optional[str] = None
    
    def get_attribute(self, key: str) -> Optional[Any]:
        attr = self.attributes.get(key)
        return attr.value if attr else None


@dataclass
class Environment:
    attributes: Dict[str, Attribute] = field(default_factory=dict)
    current_time: datetime = field(default_factory=datetime.utcnow)
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    location: Optional[str] = None


class Condition:
    def __init__(self, attribute: str, operator: str, value: Any):
        self.attribute = attribute
        self.operator = operator
        self.value = value
    
    def evaluate(self, subject: Subject, resource: Resource, environment: Environment) -> bool:
        subject_val = subject.get_attribute(self.attribute)
        resource_val = resource.get_attribute(self.attribute)
        env_val = environment.attributes.get(self.attribute, Attribute("", None)).value
        
        actual_value = subject_val or resource_val or env_val
        
        if self.operator == "eq":
            return actual_value == self.value
        elif self.operator == "ne":
            return actual_value != self.value
        elif self.operator == "in":
            return actual_value in self.value if isinstance(self.value, list) else False
        elif self.operator == "not_in":
            return actual_value not in self.value if isinstance(self.value, list) else True
        elif self.operator == "gt":
            return actual_value > self.value if actual_value is not None else False
        elif self.operator == "gte":
            return actual_value >= self.value if actual_value is not None else False
        elif self.operator == "lt":
            return actual_value < self.value if actual_value is not None else False
        elif self.operator == "lte":
            return actual_value <= self.value if actual_value is not None else False
        elif self.operator == "contains":
            return self.value in actual_value if actual_value else False
        elif self.operator == "starts_with":
            return str(actual_value).startswith(str(self.value)) if actual_value else False
        elif self.operator == "ends_with":
            return str(actual_value).endswith(str(self.value)) if actual_value else False
        elif self.operator == "matches":
            import re
            return bool(re.match(self.value, str(actual_value))) if actual_value else False
        elif self.operator == "exists":
            return actual_value is not None
        elif self.operator == "not_exists":
            return actual_value is None
        return False


@dataclass
class Policy:
    id: str
    name: str
    description: str
    effect: str
    actions: List[Action]
    resources: List[ResourceType]
    conditions: List[Condition] = field(default_factory=list)
    priority: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    is_active: bool = True


class PolicyEngine:
    def __init__(self):
        self.policies: Dict[str, Policy] = {}
        self._load_default_policies()
    
    def _load_default_policies(self):
        self.add_policy(Policy(
            id="org_admin_all",
            name="Organization Admin Full Access",
            description="Organization admins have full access to all resources in their organization",
            effect="allow",
            actions=[Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE, Action.LIST, Action.EXECUTE, Action.APPROVE, Action.REJECT],
            resources=list(ResourceType),
            conditions=[
                Condition("subject.role", "in", ["owner", "admin"]),
                Condition("subject.organization_id", "eq", "resource.organization_id"),
            ],
            priority=100,
        ))
        
        self.add_policy(Policy(
            id="owner_all",
            name="Resource Owner Full Access",
            description="Resource owners have full access to their resources",
            effect="allow",
            actions=[Action.CREATE, Action.READ, Action.UPDATE, Action.DELETE, Action.LIST, Action.EXECUTE],
            resources=list(ResourceType),
            conditions=[
                Condition("subject.id", "eq", "resource.owner_id"),
            ],
            priority=90,
        ))
        
        self.add_policy(Policy(
            id="member_read",
            name="Organization Member Read Access",
            description="Organization members can read resources in their organization",
            effect="allow",
            actions=[Action.READ, Action.LIST],
            resources=list(ResourceType),
            conditions=[
                Condition("subject.organization_id", "eq", "resource.organization_id"),
                Condition("subject.status", "eq", "active"),
            ],
            priority=50,
        ))
        
        self.add_policy(Policy(
            id="project_member_write",
            name="Project Member Write Access",
            description="Project members can update tasks and documents in their projects",
            effect="allow",
            actions=[Action.CREATE, Action.READ, Action.UPDATE, Action.LIST],
            resources=[ResourceType.TASK, ResourceType.DOCUMENT, ResourceType.PROJECT],
            conditions=[
                Condition("subject.id", "in", "resource.project.members"),
            ],
            priority=60,
        ))
        
        self.add_policy(Policy(
            id="team_lead_approve",
            name="Team Lead Approval",
            description="Team leads can approve decisions and blockers",
            effect="allow",
            actions=[Action.APPROVE, Action.REJECT],
            resources=[ResourceType.DECISION, ResourceType.BLOCKER],
            conditions=[
                Condition("subject.id", "eq", "resource.team.lead_id"),
            ],
            priority=70,
        ))
        
        self.add_policy(Policy(
            id="self_management",
            name="Self Profile Management",
            description="Users can read and update their own profile",
            effect="allow",
            actions=[Action.READ, Action.UPDATE],
            resources=[ResourceType.USER],
            conditions=[
                Condition("subject.id", "eq", "resource.id"),
            ],
            priority=80,
        ))
        
        self.add_policy(Policy(
            id="ip_restriction_admin",
            name="Admin IP Restriction",
            description="Admin actions only allowed from trusted IPs",
            effect="deny",
            actions=[Action.CREATE, Action.UPDATE, Action.DELETE, Action.APPROVE, Action.REJECT],
            resources=list(ResourceType),
            conditions=[
                Condition("subject.role", "in", ["admin", "owner"]),
                Condition("environment.ip_address", "not_in", ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]),
            ],
            priority=200,
        ))
        
        self.add_policy(Policy(
            id="time_based_access",
            name="Business Hours Access",
            description="Sensitive operations only during business hours",
            effect="deny",
            actions=[Action.DELETE, Action.APPROVE, Action.REJECT],
            resources=[ResourceType.ORGANIZATION, ResourceType.USER, ResourceType.SETTINGS],
            conditions=[
                Condition("environment.current_time.hour", "lt", 6),
            ],
            priority=150,
        ))

    def add_policy(self, policy: Policy):
        self.policies[policy.id] = policy
    
    def remove_policy(self, policy_id: str):
        if policy_id in self.policies:
            del self.policies[policy_id]
    
    def get_policy(self, policy_id: str) -> Optional[Policy]:
        return self.policies.get(policy_id)
    
    def list_policies(self) -> List[Policy]:
        return sorted(self.policies.values(), key=lambda p: -p.priority)
    
    def evaluate(
        self,
        subject: Subject,
        action: Action,
        resource: Resource,
        environment: Environment
    ) -> bool:
        applicable_policies = [
            p for p in self.list_policies()
            if p.is_active 
            and action in p.actions
            and resource.type in p.resources
        ]
        
        for policy in applicable_policies:
            if all(c.evaluate(subject, resource, environment) for c in policy.conditions):
                return policy.effect == "allow"
        
        return False


class RoleManager:
    def __init__(self, policy_engine: PolicyEngine):
        self.policy_engine = policy_engine
        self.user_roles: Dict[str, Set[str]] = {}
        self.role_permissions: Dict[str, Set[str]] = {}
        self._init_default_roles()
    
    def _init_default_roles(self):
        self.role_permissions = {
            "owner": {"*"},
            "admin": {"organization.*", "user.*", "team.*", "project.*", "task.*", "document.*", "workflow.*", "pipeline.*", "blocker.*", "decision.*", "report.*", "settings.*"},
            "manager": {"team.*", "project.*", "task.*", "document.*", "report.*", "decision.approve", "decision.reject", "blocker.*"},
            "member": {"project.read", "project.update", "task.*", "document.*", "report.read"},
            "viewer": {"*.read"},
        }
    
    def assign_role(self, user_id: str, role: str, resource_id: Optional[str] = None):
        key = f"{user_id}:{resource_id or 'global'}"
        if key not in self.user_roles:
            self.user_roles[key] = set()
        self.user_roles[key].add(role)
    
    def remove_role(self, user_id: str, role: str, resource_id: Optional[str] = None):
        key = f"{user_id}:{resource_id or 'global'}"
        if key in self.user_roles:
            self.user_roles[key].discard(role)
    
    def get_user_roles(self, user_id: str, resource_id: Optional[str] = None) -> Set[str]:
        key = f"{user_id}:{resource_id or 'global'}"
        return self.user_roles.get(key, set())
    
    def has_permission(self, user_id: str, permission: str, resource_id: Optional[str] = None) -> bool:
        roles = self.get_user_roles(user_id, resource_id)
        for role in roles:
            perms = self.role_permissions.get(role, set())
            if "*" in perms or permission in perms:
                return True
            for perm in perms:
                if perm.endswith(".*") and permission.startswith(perm[:-1]):
                    return True
        return False


class SCIMManager:
    def __init__(self, base_url: str, bearer_token: str):
        self.base_url = base_url.rstrip('/')
        self.bearer_token = bearer_token
        self.schemas = {
            "User": {
                "id": "urn:ietf:params:scim:schemas:core:2.0:User",
                "name": "User",
                "attributes": [
                    "userName", "name", "displayName", "emails", "phoneNumbers",
                    "addresses", "groups", "roles", "active", "externalId",
                    "meta", "password", "userType", "title", "preferredLanguage",
                    "locale", "timezone", "nickName", "profileUrl"
                ]
            },
            "Group": {
                "id": "urn:ietf:params:scim:schemas:core:2.0:Group",
                "name": "Group",
                "attributes": ["displayName", "members", "meta"]
            }
        }
    
    async def create_user(self, user_data: Dict) -> Dict:
        return {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], **user_data}
    
    async def get_user(self, user_id: str) -> Optional[Dict]:
        return None
    
    async def update_user(self, user_id: str, user_data: Dict) -> Dict:
        return {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "id": user_id, **user_data}
    
    async def delete_user(self, user_id: str) -> bool:
        return True
    
    async def list_users(self, filter: Optional[str] = None, start_index: int = 1, count: int = 100) -> Dict:
        return {"schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"], "totalResults": 0, "itemsPerPage": count, "startIndex": start_index, "Resources": []}
    
    async def create_group(self, group_data: Dict) -> Dict:
        return {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"], **group_data}
    
    async def get_group(self, group_id: str) -> Optional[Dict]:
        return None
    
    async def update_group(self, group_id: str, group_data: Dict) -> Dict:
        return {"schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"], "id": group_id, **group_data}
    
    async def delete_group(self, group_id: str) -> bool:
        return True
    
    async def list_groups(self, filter: Optional[str] = None, start_index: int = 1, count: int = 100) -> Dict:
        return {"schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"], "totalResults": 0, "itemsPerPage": count, "startIndex": start_index, "Resources": []}


class FIDO2Manager:
    def __init__(self, rp_id: str, rp_name: str, origin: str):
        self.rp_id = rp_id
        self.rp_name = rp_name
        self.origin = origin
        self.credentials: Dict[str, Dict] = {}
        self.challenges: Dict[str, bytes] = {}
    
    def generate_registration_challenge(self, user_id: str, user_name: str, user_display_name: str) -> Dict:
        import secrets
        challenge = secrets.token_bytes(32)
        self.challenges[user_id] = challenge
        
        return {
            "challenge": challenge.hex(),
            "rp": {"id": self.rp_id, "name": self.rp_name},
            "user": {"id": user_id, "name": user_name, "displayName": user_display_name},
            "pubKeyCredParams": [
                {"type": "public-key", "alg": -7},
                {"type": "public-key", "alg": -257},
            ],
            "timeout": 60000,
            "attestation": "direct",
            "authenticatorSelection": {
                "authenticatorAttachment": "platform",
                "requireResidentKey": True,
                "userVerification": "preferred",
            },
        }
    
    def verify_registration(self, user_id: str, attestation_object: str, client_data_json: str) -> Optional[str]:
        if user_id not in self.challenges:
            return None
        expected_challenge = self.challenges[user_id]
        del self.challenges[user_id]
        
        import base64
        import json
        
        client_data = json.loads(base64.urlsafe_b64decode(client_data_json + '==').decode())
        if client_data.get('challenge') != expected_challenge.hex():
            return None
        
        credential_id = secrets.token_bytes(16).hex()
        self.credentials[credential_id] = {
            "user_id": user_id,
            "credential_id": credential_id,
            "public_key": "mock_public_key",
            "sign_count": 0,
        }
        
        return credential_id
    
    def generate_authentication_challenge(self, user_id: str) -> Optional[Dict]:
        if not any(c["user_id"] == user_id for c in self.credentials.values()):
            return None
        
        import secrets
        challenge = secrets.token_bytes(32)
        self.challenges[user_id] = challenge
        
        allowed_credentials = [
            {"type": "public-key", "id": cred_id}
            for cred_id, cred in self.credentials.items()
            if cred["user_id"] == user_id
        ]
        
        return {
            "challenge": challenge.hex(),
            "timeout": 60000,
            "rpId": self.rp_id,
            "allowCredentials": allowed_credentials,
            "userVerification": "preferred",
        }
    
    def verify_authentication(self, user_id: str, credential_id: str, authenticator_data: str, client_data_json: str, signature: str) -> bool:
        if user_id not in self.challenges:
            return False
        
        expected_challenge = self.challenges[user_id]
        del self.challenges[user_id]
        
        import base64
        import json
        
        client_data = json.loads(base64.urlsafe_b64decode(client_data_json + '==').decode())
        if client_data.get('challenge') != expected_challenge.hex():
            return False
        
        if credential_id not in self.credentials:
            return False
        
        cred = self.credentials[credential_id]
        cred["sign_count"] += 1
        
        return True


import secrets
from typing import Dict, Set, Optional, Any
from datetime import datetime


policy_engine = PolicyEngine()
role_manager = RoleManager(policy_engine)
scim_manager = SCIMManager("https://api.vcos.io", "scim_token")
fido2_manager = FIDO2Manager("vcos.io", "VCOS", "https://app.vcos.io")