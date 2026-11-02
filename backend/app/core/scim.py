"""SCIM 2.0 Provisioning Service."""

import logging
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from pydantic.alias_generators import to_camel

from app.core.config import get_settings
from app.core.presence_redis import PresenceService

logger = logging.getLogger(__name__)


class SCIMVersion(str, Enum):
    V2 = "2.0"


class SCIMResourceType(str, Enum):
    USER = "User"
    GROUP = "Group"


class SCIMSchema(BaseModel):
    """SCIM Schema definition."""
    id: str
    name: str
    description: str = ""
    attributes: List[Dict[str, Any]] = []
    meta: Dict[str, Any] = field(default_factory=dict)


class SCIMResource(BaseModel):
    """Base SCIM Resource."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = []
    id: Optional[str] = None
    external_id: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


class SCIMUser(SCIMResource):
    """SCIM User Resource."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = ["urn:ietf:params:scim:schemas:core:2.0:User"]
    user_name: str
    name: Dict[str, str] = {}
    display_name: Optional[str] = None
    nick_name: Optional[str] = None
    profile_url: Optional[str] = None
    title: Optional[str] = None
    user_type: Optional[str] = None
    preferred_language: Optional[str] = None
    locale: Optional[str] = None
    timezone: Optional[str] = None
    active: bool = True
    emails: List[Dict[str, Any]] = []
    phone_numbers: List[Dict[str, Any]] = []
    addresses: List[Dict[str, Any]] = []
    groups: List[Dict[str, Any]] = []
    roles: List[Dict[str, Any]] = []
    entitlements: List[Dict[str, Any]] = []
    x509_certificates: List[Dict[str, Any]] = []


class SCIMGroup(SCIMResource):
    """SCIM Group Resource."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = ["urn:ietf:params:scim:schemas:core:2.0:Group"]
    display_name: str
    members: List[Dict[str, Any]] = []


class SCIMListResponse(BaseModel):
    """SCIM List Response."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = ["urn:ietf:params:scim:api:messages:2.0:ListResponse"]
    total_results: int
    start_index: int = 1
    items_per_page: int
    resources: List[Dict[str, Any]] = []


class SCIMError(BaseModel):
    """SCIM Error Response."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = ["urn:ietf:params:scim:api:messages:2.0:Error"]
    detail: str
    status: int
    scim_type: Optional[str] = None


class SCIMUserCreate(BaseModel):
    """SCIM User Create Request."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = ["urn:ietf:params:scim:schemas:core:2.0:User"]
    user_name: str
    name: Dict[str, str] = {}
    display_name: Optional[str] = None
    emails: List[Dict[str, Any]] = []
    active: bool = True
    external_id: Optional[str] = None
    groups: List[Dict[str, Any]] = []
    roles: List[Dict[str, Any]] = []


class SCIMUserUpdate(BaseModel):
    """SCIM User Update Request (PATCH)."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = ["urn:ietf:params:scim:api:messages:2.0:PatchOp"]
    operations: List[Dict[str, Any]]


class SCIMGroupCreate(BaseModel):
    """SCIM Group Create Request."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = ["urn:ietf:params:scim:schemas:core:2.0:Group"]
    display_name: str
    members: List[Dict[str, Any]] = []


class SCIMServiceProviderConfig(BaseModel):
    """SCIM Service Provider Configuration."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)
    
    schemas: List[str] = ["urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"]
    patch: Dict[str, bool] = {"supported": True}
    bulk: Dict[str, Any] = {"supported": False, "maxOperations": 1000, "maxPayloadSize": 1048576}
    filter: Dict[str, Any] = {"supported": True, "maxResults": 100}
    change_password: Dict[str, bool] = {"supported": False}
    sort: Dict[str, bool] = {"supported": False}
    etag: Dict[str, bool] = {"supported": False}
    authentication_schemes: List[Dict[str, Any]] = [
        {"type": "oauthbearertoken", "name": "OAuth Bearer Token", "description": "Authentication using OAuth 2.0 Bearer Token"}
    ]


class SCIMService:
    """SCIM 2.0 Provisioning Service."""
    
    def __init__(self):
        self.users: Dict[str, SCIMUser] = {}
        self.groups: Dict[str, SCIMGroup] = {}
        self.external_id_map: Dict[str, str] = {}  # external_id -> user_id
        self.user_group_map: Dict[str, Set[str]] = {}  # user_id -> group_ids
        self.group_user_map: Dict[str, Set[str]] = {}  # group_id -> user_ids
    
    # =========================================================================
    # User Operations
    # =========================================================================
    
    async def create_user(self, user_data: SCIMUserCreate) -> SCIMUser:
        """Create a new SCIM user."""
        # Check if user_name already exists
        for user in self.users.values():
            if user.user_name == user_data.user_name:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"User with userName '{user_data.user_name}' already exists"
                )
        
        # Check external_id uniqueness
        if user_data.external_id and user_data.external_id in self.external_id_map:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"User with externalId '{user_data.external_id}' already exists"
            )
        
        user_id = str(uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        
        user = SCIMUser(
            id=user_id,
            external_id=user_data.external_id,
            user_name=user_data.user_name,
            name=user_data.name,
            display_name=user_data.display_name,
            emails=user_data.emails,
            active=user_data.active,
            meta={
                "resourceType": "User",
                "created": now,
                "lastModified": now,
                "location": f"/scim/v2/Users/{user_id}",
                "version": str(uuid4()),
            }
        )
        
        self.users[user_id] = user
        self.external_id_map[user_data.external_id] = user_id
        self.user_group_map[user_id] = set()
        
        logger.info(f"Created SCIM user: {user_id} ({user_data.user_name})")
        return user
    
    async def get_user(self, user_id: str) -> SCIMUser:
        """Get user by ID."""
        if user_id not in self.users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        return self.users[user_id]
    
    async def get_user_by_external_id(self, external_id: str) -> Optional[SCIMUser]:
        """Get user by external ID."""
        user_id = self.external_id_map.get(external_id)
        if user_id:
            return self.users.get(user_id)
        return None
    
    async def list_users(
        self,
        start_index: int = 1,
        count: int = 100,
        filter: Optional[str] = None,
    ) -> SCIMListResponse:
        """List users with optional filtering."""
        users = list(self.users.values())
        
        # Apply filter if provided (simplified - only supports userName eq)
        if filter:
            match = re.search(r'userName\s+eq\s+"([^"]+)"', filter)
            if match:
                filter_value = match.group(1)
                users = [u for u in users if u.user_name == filter_value]
        
        total = len(users)
        start = max(0, start_index - 1)
        end = min(start + count, total)
        resources = [u.model_dump(exclude_none=True) for u in users[start:end]]
        
        return SCIMListResponse(
            total_results=total,
            start_index=start_index,
            items_per_page=count,
            resources=resources,
        )
    
    async def update_user(self, user_id: str, user_data: SCIMUserCreate) -> SCIMUser:
        """Update user (PUT - replace)."""
        if user_id not in self.users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        user = self.users[user_id]
        
        # Check user_name conflict
        if user_data.user_name != user.user_name:
            for u in self.users.values():
                if u.user_name == user_data.user_name:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"User with userName '{user_data.user_name}' already exists"
                    )
        
        # Update fields
        user.user_name = user_data.user_name
        user.name = user_data.name
        user.display_name = user_data.display_name
        user.emails = user_data.emails
        user.active = user_data.active
        user.external_id = user_data.external_id
        
        # Update external_id map
        if user_data.external_id:
            self.external_id_map[user_data.external_id] = user_id
        
        user.meta["lastModified"] = datetime.utcnow().isoformat() + "Z"
        user.meta["version"] = str(uuid4())
        
        logger.info(f"Updated SCIM user: {user_id}")
        return user
    
    async def patch_user(self, user_id: str, operations: List[Dict[str, Any]]) -> SCIMUser:
        """Partially update user (PATCH)."""
        if user_id not in self.users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        user = self.users[user_id]
        
        for op in operations:
            op_type = op.get("op")
            path = op.get("path", "")
            value = op.get("value")
            
            if op_type == "add":
                if path == "emails":
                    user.emails.extend(value if isinstance(value, list) else [value])
                elif path == "phoneNumbers":
                    user.phone_numbers = user.phone_numbers or []
                    user.phone_numbers.extend(value if isinstance(value, list) else [value])
                elif path == "groups":
                    for group_ref in value:
                        group_id = group_ref.get("value")
                        if group_id and group_id in self.groups:
                            self.user_group_map.setdefault(user_id, set()).add(group_id)
                            self.group_user_map.setdefault(group_id, set()).add(user_id)
                elif not path or path == "":
                    # Add multiple attributes
                    if isinstance(value, dict):
                        for k, v in value.items():
                            if hasattr(user, k):
                                setattr(user, k, v)
            
            elif op_type == "replace":
                if path == "userName":
                    user.user_name = value
                elif path == "displayName":
                    user.display_name = value
                elif path == "active":
                    user.active = value
                elif path == "emails":
                    user.emails = value
                elif path == "name":
                    user.name = value
                elif path == "":
                    # Replace all
                    for k, v in value.items():
                        if hasattr(user, k):
                            setattr(user, k, v)
            
            elif op_type == "remove":
                if path == "emails" and value:
                    user.emails = [e for e in user.emails if e.get("value") != value]
                elif path == "groups" and value:
                    group_id = value
                    if group_id in self.group_user_map:
                        self.group_user_map[group_id].discard(user_id)
                    self.user_group_map.get(user_id, set()).discard(group_id)
                elif path == "":
                    # Remove all attributes in value
                    if isinstance(value, dict):
                        for k in value.keys():
                            if hasattr(user, k):
                                setattr(user, k, None)
        
        user.meta["lastModified"] = datetime.utcnow().isoformat() + "Z"
        user.meta["version"] = str(uuid4())
        
        logger.info(f"Patched SCIM user: {user_id}")
        return user
    
    async def delete_user(self, user_id: str) -> bool:
        """Delete a user."""
        if user_id not in self.users:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        user = self.users.pop(user_id)
        
        # Clean up external_id map
        if user.external_id:
            self.external_id_map.pop(user.external_id, None)
        
        # Clean up group memberships
        if user_id in self.user_group_map:
            for group_id in self.user_group_map[user_id]:
                if group_id in self.group_user_map:
                    self.group_user_map[group_id].discard(user_id)
            del self.user_group_map[user_id]
        
        logger.info(f"Deleted SCIM user: {user_id}")
        return True
    
    # =========================================================================
    # Group Operations
    # =========================================================================
    
    async def create_group(self, group_data: SCIMGroupCreate) -> SCIMGroup:
        """Create a new SCIM group."""
        group_id = str(uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        
        group = SCIMGroup(
            id=group_id,
            display_name=group_data.display_name,
            members=group_data.members,
            meta={
                "resourceType": "Group",
                "created": now,
                "lastModified": now,
                "location": f"/scim/v2/Groups/{group_id}",
                "version": str(uuid4()),
            }
        )
        
        self.groups[group_id] = group
        self.group_user_map[group_id] = set()
        
        # Add members
        for member_ref in group_data.members:
            user_id = member_ref.get("value")
            if user_id and user_id in self.users:
                self.group_user_map[group_id].add(user_id)
                self.user_group_map.setdefault(user_id, set()).add(group_id)
        
        logger.info(f"Created SCIM group: {group_id} ({group_data.display_name})")
        return group
    
    async def get_group(self, group_id: str) -> SCIMGroup:
        """Get group by ID."""
        if group_id not in self.groups:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group {group_id} not found"
            )
        return self.groups[group_id]
    
    async def list_groups(
        self,
        start_index: int = 1,
        count: int = 100,
        filter: Optional[str] = None,
    ) -> SCIMListResponse:
        """List groups with optional filtering."""
        groups = list(self.groups.values())
        
        if filter:
            match = re.search(r'displayName\s+eq\s+"([^"]+)"', filter)
            if match:
                filter_value = match.group(1)
                groups = [g for g in groups if g.display_name == filter_value]
        
        total = len(groups)
        start = max(0, start_index - 1)
        end = min(start + count, total)
        resources = [g.model_dump(exclude_none=True) for g in groups[start:end]]
        
        return SCIMListResponse(
            total_results=total,
            start_index=start_index,
            items_per_page=count,
            resources=resources,
        )
    
    async def update_group(self, group_id: str, group_data: SCIMGroupCreate) -> SCIMGroup:
        """Update group (PUT - replace)."""
        if group_id not in self.groups:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group {group_id} not found"
            )
        
        group = self.groups[group_id]
        group.display_name = group_data.display_name
        
        # Update members
        old_members = self.group_user_map.get(group_id, set())
        new_members = set()
        
        for member_ref in group_data.members:
            user_id = member_ref.get("value")
            if user_id and user_id in self.users:
                new_members.add(user_id)
        
        # Remove old members not in new list
        for user_id in old_members - new_members:
            if user_id in self.user_group_map:
                self.user_group_map[user_id].discard(group_id)
        
        # Add new members
        for user_id in new_members - old_members:
            self.user_group_map.setdefault(user_id, set()).add(group_id)
        
        self.group_user_map[group_id] = new_members
        group.members = [{"value": uid, "$ref": f"/scim/v2/Users/{uid}"} for uid in new_members]
        group.meta["lastModified"] = datetime.utcnow().isoformat() + "Z"
        
        logger.info(f"Updated SCIM group: {group_id}")
        return group
    
    async def patch_group(self, group_id: str, operations: List[Dict[str, Any]]) -> SCIMGroup:
        """Partially update group (PATCH)."""
        if group_id not in self.groups:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group {group_id} not found"
            )
        
        group = self.groups[group_id]
        
        for op in operations:
            op_type = op.get("op")
            path = op.get("path", "")
            value = op.get("value")
            
            if op_type == "add" and path == "members":
                for member_ref in value:
                    user_id = member_ref.get("value")
                    if user_id and user_id in self.users:
                        self.group_user_map[group_id].add(user_id)
                        self.user_group_map.setdefault(user_id, set()).add(group_id)
            
            elif op_type == "remove" and path == "members":
                user_id = value
                if user_id in self.group_user_map.get(group_id, set()):
                    self.group_user_map[group_id].discard(user_id)
                    if user_id in self.user_group_map:
                        self.user_group_map[user_id].discard(group_id)
        
        group.meta["lastModified"] = datetime.utcnow().isoformat() + "Z"
        group.members = [{"value": uid, "$ref": f"/scim/v2/Users/{uid}"} for uid in self.group_user_map.get(group_id, set())]
        
        logger.info(f"Patched SCIM group: {group_id}")
        return group
    
    async def delete_group(self, group_id: str) -> bool:
        """Delete a group."""
        if group_id not in self.groups:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Group {group_id} not found"
            )
        
        # Remove from all users
        for user_id in self.group_user_map.get(group_id, set()):
            if user_id in self.user_group_map:
                self.user_group_map[user_id].discard(group_id)
        
        self.groups.pop(group_id)
        self.group_user_map.pop(group_id, None)
        
        logger.info(f"Deleted SCIM group: {group_id}")
        return True


# Global SCIM service instance
_scim_service: Optional["SCIMService"] = None


def get_scim_service() -> "SCIMService":
    """Get global SCIM service instance."""
    global _scim_service
    if _scim_service is None:
        _scim_service = SCIMService()
    return _scim_service