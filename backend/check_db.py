import asyncio
from app.db.database import get_db
from sqlalchemy import select
from app.models.role import UserRoleModel, Role, RolePermission, Permission
from app.models.permission_helpers import user_permission_codes

async def check():
    async for db in get_db():
        # Check UserRoleModel
        result = await db.execute(select(UserRoleModel))
        user_roles = result.scalars().all()
        print(f'UserRoleModel count: {len(user_roles)}')
        for ur in user_roles:
            print(f'  user_id={ur.user_id}, role_id={ur.role_id}, org_id={ur.organization_id}')
        
        # Check roles
        result = await db.execute(select(Role))
        roles = result.scalars().all()
        print(f'Role count: {len(roles)}')
        for r in roles:
            print(f'  id={r.id}, code={r.code}, org_id={r.organization_id}')
        
        # Check permissions
        result = await db.execute(select(Permission))
        perms = result.scalars().all()
        print(f'Permission count: {len(perms)}')
        for p in perms:
            print(f'  id={p.id}, code={p.code}, org_id={p.organization_id}')
        
        # Check role_permissions
        result = await db.execute(select(RolePermission))
        rps = result.scalars().all()
        print(f'RolePermission count: {len(rps)}')
        for rp in rps:
            print(f'  role_id={rp.role_id}, perm_id={rp.permission_id}')
        
        # Check user permissions for test user
        test_user_id = 'da0bbf06-a120-4be0-a0b3-94535cf946ab'
        test_org_id = 'dd150b11-68da-4378-8ef6-7c67c31df555'
        codes = await user_permission_codes(db, organization_id=test_org_id, user_id=test_user_id)
        print(f'User permissions for {test_user_id}: {codes}')
        break

asyncio.run(check())