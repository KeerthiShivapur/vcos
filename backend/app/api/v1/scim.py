"""SCIM 2.0 API Router."""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse

from app.core.scim import (
    SCIMService,
    SCIMUser,
    SCIMUserCreate,
    SCIMUserUpdate,
    SCIMGroup,
    SCIMGroupCreate,
    SCIMListResponse,
    SCIMServiceProviderConfig,
    get_scim_service,
)

router = APIRouter(prefix="/scim/v2", tags=["scim"])


# =========================================================================
# Service Provider Config
# =========================================================================

@router.get("/ServiceProviderConfig", response_model=SCIMServiceProviderConfig)
async def get_service_provider_config():
    """Get SCIM Service Provider Configuration."""
    return SCIMServiceProviderConfig()


# =========================================================================
# Schemas
# =========================================================================

@router.get("/Schemas")
async def list_schemas():
    """List SCIM schemas."""
    return {
        "schemas": [
            {
                "id": "urn:ietf:params:scim:schemas:core:2.0:User",
                "name": "User",
                "description": "User Account",
                "attributes": [
                    {"name": "userName", "type": "string", "required": True, "uniqueness": "server", "caseExact": False},
                    {"name": "name", "type": "complex", "subAttributes": [
                        {"name": "formatted", "type": "string"},
                        {"name": "familyName", "type": "string"},
                        {"name": "givenName", "type": "string"},
                        {"name": "middleName", "type": "string"},
                        {"name": "honorificPrefix", "type": "string"},
                        {"name": "honorificSuffix", "type": "string"},
                    ]},
                    {"name": "displayName", "type": "string"},
                    {"name": "emails", "type": "complex", "multiValued": True, "subAttributes": [
                        {"name": "value", "type": "string"},
                        {"name": "type", "type": "string"},
                        {"name": "primary", "type": "boolean"},
                    ]},
                    {"name": "active", "type": "boolean"},
                ],
            },
            {
                "id": "urn:ietf:params:scim:schemas:core:2.0:Group",
                "name": "Group",
                "description": "Group",
                "attributes": [
                    {"name": "displayName", "type": "string", "required": True},
                    {"name": "members", "type": "complex", "multiValued": True, "subAttributes": [
                        {"name": "value", "type": "string"},
                        {"name": "$ref", "type": "reference"},
                        {"name": "display", "type": "string"},
                    ]},
                ],
            },
        ]
    }


@router.get("/Schemas/{schema_id}")
async def get_schema(schema_id: str):
    """Get a specific schema."""
    # In a real implementation, this would fetch from a schema registry
    raise HTTPException(status_code=404, detail="Schema not found")


# =========================================================================
# Users
# =========================================================================

@router.post("/Users", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: SCIMUserCreate,
    scim: SCIMService = Depends(get_scim_service),
):
    """Create a new user."""
    user = await scim.create_user(user_data)
    return user.model_dump(exclude_none=True)


@router.get("/Users")
async def list_users(
    start_index: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=1000),
    filter: Optional[str] = Query(None),
    scim: SCIMService = Depends(get_scim_service),
):
    """List users with pagination and filtering."""
    response = await scim.list_users(start_index=start_index, count=count, filter=filter)
    return response.model_dump(exclude_none=True)


@router.get("/Users/{user_id}")
async def get_user(
    user_id: str,
    scim: SCIMService = Depends(get_scim_service),
):
    """Get a user by ID."""
    user = await scim.get_user(user_id)
    return user.model_dump(exclude_none=True)


@router.put("/Users/{user_id}")
async def replace_user(
    user_id: str,
    user_data: SCIMUserCreate,
    scim: SCIMService = Depends(get_scim_service),
):
    """Replace a user (PUT)."""
    user = await scim.update_user(user_id, user_data)
    return user.model_dump(exclude_none=True)


@router.patch("/Users/{user_id}")
async def patch_user(
    user_id: str,
    user_data: SCIMUserUpdate,
    scim: SCIMService = Depends(get_scim_service),
):
    """Partially update a user (PATCH)."""
    user = await scim.patch_user(user_id, user_data.operations)
    return user.model_dump(exclude_none=True)


@router.delete("/Users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    scim: SCIMService = Depends(get_scim_service),
):
    """Delete a user."""
    await scim.delete_user(user_id)
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================================
# Groups
# =========================================================================

@router.post("/Groups", response_model=dict, status_code=status.HTTP_201_CREATED)
async def create_group(
    group_data: SCIMGroupCreate,
    scim: SCIMService = Depends(get_scim_service),
):
    """Create a new group."""
    group = await scim.create_group(group_data)
    return group.model_dump(exclude_none=True)


@router.get("/Groups")
async def list_groups(
    start_index: int = Query(1, ge=1),
    count: int = Query(100, ge=1, le=1000),
    filter: Optional[str] = Query(None),
    scim: SCIMService = Depends(get_scim_service),
):
    """List groups with pagination and filtering."""
    response = await scim.list_groups(start_index=start_index, count=count, filter=filter)
    return response.model_dump(exclude_none=True)


@router.get("/Groups/{group_id}")
async def get_group(
    group_id: str,
    scim: SCIMService = Depends(get_scim_service),
):
    """Get a group by ID."""
    group = await scim.get_group(group_id)
    return group.model_dump(exclude_none=True)


@router.put("/Groups/{group_id}")
async def replace_group(
    group_id: str,
    group_data: SCIMGroupCreate,
    scim: SCIMService = Depends(get_scim_service),
):
    """Replace a group (PUT)."""
    group = await scim.update_group(group_id, group_data)
    return group.model_dump(exclude_none=True)


@router.patch("/Groups/{group_id}")
async def patch_group(
    group_id: str,
    operations: dict,  # SCIMUserUpdate with operations
    scim: SCIMService = Depends(get_scim_service),
):
    """Partially update a group (PATCH)."""
    # Parse operations from request body
    operations = operations.get("operations", [])
    group = await scim.patch_group(group_id, operations)
    return group.model_dump(exclude_none=True)


@router.delete("/Groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    scim: SCIMService = Depends(get_scim_service),
):
    """Delete a group."""
    await scim.delete_group(group_id)
    return JSONResponse(status_code=status.HTTP_204_NO_CONTENT)


# =========================================================================
# Bulk Operations (Optional)
# =========================================================================

@router.post("/Bulk", status_code=status.HTTP_200_OK)
async def bulk_operations(
    request: Request,
    scim: SCIMService = Depends(get_scim_service),
):
    """Process bulk operations (optional)."""
    body = await request.json()
    # In a real implementation, process bulk operations
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkResponse"],
        "operations": [],
    }