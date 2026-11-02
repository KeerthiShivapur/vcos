"""Permission Service - Centralized permission checking."""

import logging
from typing import List, Optional, Set
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.organization import Organization
from app.models.user import User, UserRole

logger = logging.getLogger("vcos.permissions")


class PermissionService:
    """Service for checking user permissions."""
    
    # Role hierarchy (higher number = more permissions)
    ROLE_HIERARCHY = {
        UserRole.VIEWER: 0,
        UserRole.MEMBER: 10,
        UserRole.MANAGER: 20,
        UserRole.ADMIN: 30,
        UserRole.CEO: 35,
        UserRole.OWNER: 40,
    }
    
    # Permission mappings by role
    ROLE_PERMISSIONS = {
        UserRole.VIEWER: {
            "workspace:read",
            "project:read",
            "task:read",
            "document:read",
        },
        UserRole.MEMBER: {
            "workspace:read",
            "workspace:write",
            "project:read",
            "project:write",
            "task:read",
            "task:write",
            "document:read",
            "document:write",
            "meeting:read",
            "meeting:write",
        },
        UserRole.MANAGER: {
            "workspace:read",
            "workspace:write",
            "workspace:manage",
            "project:read",
            "project:write",
            "project:manage",
            "task:read",
            "task:write",
            "task:manage",
            "document:read",
            "document:write",
            "document:manage",
            "meeting:read",
            "meeting:write",
            "meeting:manage",
            "team:read",
            "team:write",
            "team:manage",
            "approval:read",
            "approval:write",
            "approval:approve",
            "approval:manage",
        },
        UserRole.ADMIN: {
            "*",  # All permissions
        },
        UserRole.CEO: {
            "*",  # All permissions
        },
        UserRole.OWNER: {
            "*",  # All permissions
        },
    }

    def __init__(self):
        self._permission_cache: dict[str, Set[str]] = {}

    def get_user_permissions(self, user: User) -> Set[str]:
        """Get all permissions for a user based on their role."""
        role = user.role if user.role else UserRole.MEMBER
        return self.ROLE_PERMISSIONS.get(role, set())

    def has_permission(self, user: User, permission: str) -> bool:
        """Check if user has a specific permission."""
        user_permissions = self.get_user_permissions(user)
        
        # Admin and Owner have all permissions
        if "*" in user_permissions:
            return True
        
        return permission in user_permissions

    def has_any_permission(self, user: User, permissions: List[str]) -> bool:
        """Check if user has any of the given permissions."""
        user_permissions = self.get_user_permissions(user)
        
        if "*" in user_permissions:
            return True
        
        return any(p in user_permissions for p in permissions)

    def has_all_permissions(self, user: User, permissions: List[str]) -> bool:
        """Check if user has all of the given permissions."""
        user_permissions = self.get_user_permissions(user)
        
        if "*" in user_permissions:
            return True
        
        return all(p in user_permissions for p in permissions)

    def get_role_level(self, role: UserRole) -> int:
        """Get the hierarchy level of a role."""
        return self.ROLE_HIERARCHY.get(role, 0)

    def can_manage_user(self, actor: User, target: User) -> bool:
        """Check if actor can manage target user."""
        actor_level = self.get_role_level(actor.role if actor.role else UserRole.MEMBER)
        target_level = self.get_role_level(target.role if target.role else UserRole.MEMBER)
        
        # Can only manage users with lower role level
        return actor_level > target_level

    def get_effective_permissions(self, user: User, organization_id: str) -> Set[str]:
        """Get effective permissions considering organization-level overrides."""
        # Start with role-based permissions
        permissions = self.get_user_permissions(user)
        
        # TODO: Add organization-level permission overrides
        # TODO: Add project/team specific permissions
        
        return permissions

    async def user_permission_codes(self, db: AsyncSession, organization_id: str, user_id: str) -> set[str]:
        """Get effective permission codes for a user in an organization."""
        from app.models.permission_helpers import user_permission_codes as upc
        return await upc(db, organization_id=organization_id, user_id=user_id)

    async def seed_org_roles(self, db: AsyncSession, organization_id: str) -> dict:
        """Create default system roles for a new organization with permissions."""
        from app.models.role import Role, RolePermission, Permission
        
        # Default system permissions
        permissions_config = {
            # Knowledge permissions
            "knowledge:read": {"name": "Read Knowledge", "resource_type": "knowledge", "action": "read", "scope": "organization"},
            "knowledge:manage": {"name": "Manage Knowledge", "resource_type": "knowledge", "action": "manage", "scope": "organization"},
            "knowledge:write": {"name": "Write Knowledge", "resource_type": "knowledge", "action": "write", "scope": "organization"},
            
            # Workspace permissions
            "workspace:read": {"name": "Read Workspace", "resource_type": "workspace", "action": "read", "scope": "organization"},
            "workspace:write": {"name": "Write Workspace", "resource_type": "workspace", "action": "write", "scope": "organization"},
            "workspace:manage": {"name": "Manage Workspace", "resource_type": "workspace", "action": "manage", "scope": "organization"},
            
            # Project permissions
            "project:read": {"name": "Read Project", "resource_type": "project", "action": "read", "scope": "organization"},
            "project:write": {"name": "Write Project", "resource_type": "project", "action": "write", "scope": "organization"},
            "project:manage": {"name": "Manage Project", "resource_type": "project", "action": "manage", "scope": "organization"},
            
            # Task permissions
            "task:read": {"name": "Read Task", "resource_type": "task", "action": "read", "scope": "organization"},
            "task:write": {"name": "Write Task", "resource_type": "task", "action": "write", "scope": "organization"},
            "task:manage": {"name": "Manage Task", "resource_type": "task", "action": "manage", "scope": "organization"},
            
            # Document permissions
            "document:read": {"name": "Read Document", "resource_type": "document", "action": "read", "scope": "organization"},
            "document:write": {"name": "Write Document", "resource_type": "document", "action": "write", "scope": "organization"},
            "document:manage": {"name": "Manage Document", "resource_type": "document", "action": "manage", "scope": "organization"},
            
            # Meeting permissions
            "meeting:read": {"name": "Read Meeting", "resource_type": "meeting", "action": "read", "scope": "organization"},
            "meeting:write": {"name": "Write Meeting", "resource_type": "meeting", "action": "write", "scope": "organization"},
            "meeting:manage": {"name": "Manage Meeting", "resource_type": "meeting", "action": "manage", "scope": "organization"},
            
            # Team permissions
            "team:read": {"name": "Read Team", "resource_type": "team", "action": "read", "scope": "organization"},
            "team:write": {"name": "Write Team", "resource_type": "team", "action": "write", "scope": "organization"},
            "team:manage": {"name": "Manage Team", "resource_type": "team", "action": "manage", "scope": "organization"},
            
            # Approval permissions
            "approval:read": {"name": "Read Approval", "resource_type": "approval", "action": "read", "scope": "organization"},
            "approval:write": {"name": "Write Approval", "resource_type": "approval", "action": "write", "scope": "organization"},
            "approval:approve": {"name": "Approve Approval", "resource_type": "approval", "action": "approve", "scope": "organization"},
            "approval:manage": {"name": "Manage Approval", "resource_type": "approval", "action": "manage", "scope": "organization"},
            
            # Calendar permissions
            "calendar:read": {"name": "Read Calendar", "resource_type": "calendar", "action": "read", "scope": "organization"},
            "calendar:manage": {"name": "Manage Calendar", "resource_type": "calendar", "action": "manage", "scope": "organization"},
            
            # AI permissions
            "ai:use": {"name": "Use AI", "resource_type": "ai", "action": "use", "scope": "organization"},
            
            # Search permissions
            "search:global": {"name": "Global Search", "resource_type": "search", "action": "global", "scope": "organization"},
            
            # Intelligence permissions
            "intelligence:read": {"name": "Read Intelligence", "resource_type": "intelligence", "action": "read", "scope": "organization"},
            "intelligence:manage": {"name": "Manage Intelligence", "resource_type": "intelligence", "action": "manage", "scope": "organization"},
        }
        
        # Role -> permissions mapping
        role_permissions_map = {
            "ceo": list(permissions_config.keys()),  # CEO gets all permissions
            "admin": list(permissions_config.keys()),  # Admin gets all permissions
            "manager": [
                "knowledge:read", "knowledge:write", "knowledge:manage",
                "workspace:read", "workspace:write", "workspace:manage",
                "project:read", "project:write", "project:manage",
                "task:read", "task:write", "task:manage",
                "document:read", "document:write", "document:manage",
                "meeting:read", "meeting:write", "meeting:manage",
                "team:read", "team:write", "team:manage",
                "approval:read", "approval:write", "approval:approve", "approval:manage",
                "calendar:read", "calendar:manage",
                "ai:use",
                "search:global",
                "intelligence:read", "intelligence:manage",
            ],
            "member": [
                "knowledge:read", "knowledge:write",
                "workspace:read", "workspace:write",
                "project:read", "project:write",
                "task:read", "task:write",
                "document:read", "document:write",
                "meeting:read", "meeting:write",
                "ai:use",
                "search:global",
            ],
            "viewer": [
                "knowledge:read",
                "workspace:read",
                "project:read",
                "task:read",
                "document:read",
                "meeting:read",
                "search:global",
            ],
        }
        
        # Default system roles
        roles_config = {
            "ceo": {
                "name": "CEO",
                "description": "Chief Executive Officer - Full organization access",
                "code": "ceo",
                "is_system": True,
                "is_default": False,
                "priority": 100,
            },
            "admin": {
                "name": "Administrator",
                "description": "Organization administrator",
                "code": "admin",
                "is_system": True,
                "is_default": False,
                "priority": 80,
            },
            "manager": {
                "name": "Manager",
                "description": "Team/Department manager",
                "code": "manager",
                "is_system": True,
                "is_default": False,
                "priority": 60,
            },
            "member": {
                "name": "Member",
                "description": "Regular organization member",
                "code": "member",
                "is_system": True,
                "is_default": True,
                "priority": 40,
            },
            "viewer": {
                "name": "Viewer",
                "description": "Read-only access",
                "code": "viewer",
                "is_system": True,
                "is_default": False,
                "priority": 20,
            },
        }
        
        created_roles = {}
        created_permissions = {}
        
        # Create permissions first
        for perm_code, perm_data in permissions_config.items():
            perm = Permission(
                organization_id=organization_id,
                code=perm_code,
                name=perm_data["name"],
                resource_type=perm_data["resource_type"],
                action=perm_data["action"],
                scope=perm_data["scope"],
                is_system=True,
            )
            db.add(perm)
            await db.flush()
            created_permissions[perm_code] = perm
        
        # Create roles and assign permissions
        for role_key, role_data in roles_config.items():
            role = Role(
                organization_id=organization_id,
                **role_data
            )
            db.add(role)
            await db.flush()
            
            # Assign permissions to role
            for perm_code in role_permissions_map.get(role_key, []):
                if perm_code in created_permissions:
                    role_perm = RolePermission(
                        role_id=role.id,
                        permission_id=created_permissions[perm_code].id,
                    )
                    db.add(role_perm)
            
            await db.flush()
            created_roles[role_key] = role
        
        return created_roles


permission_service = PermissionService()