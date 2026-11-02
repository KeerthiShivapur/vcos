"""
Embedded Analytics API Endpoints.

Provides:
- Embedded dashboard management
- White-label branding configuration
- SSO/JWT token generation
- Embedding HTML/JS generation
- Embedding security (CORS, CSP)
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.core.embedded_analytics import (
    EmbeddedAnalyticsManager,
    EmbeddedDashboardConfig,
    BrandingConfig,
    SSOConfig,
    EmbedTokenPayload,
    EmbeddingMode,
    EmbeddingTheme,
    SSOProvider,
    get_embedded_analytics,
    init_embedded_analytics,
)
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/embedded-analytics", tags=["Embedded Analytics"])


# ==================== Request/Response Models ====================

class EmbeddedDashboardCreate(BaseModel):
    name: str
    description: Optional[str] = None
    dashboard_id: Optional[str] = None
    dashboard_config: Dict[str, Any] = {}
    embedding_mode: str = "iframe"
    allowed_origins: List[str] = ["*"]
    theme: str = "auto"
    branding: Optional[Dict[str, Any]] = None
    allow_fullscreen: bool = True
    allow_export: bool = True
    allow_share: bool = True
    allow_drill_down: bool = True
    allow_filtering: bool = True
    auto_refresh: bool = False
    refresh_interval_seconds: int = 300
    width: str = "100%"
    height: str = "600px"
    min_height: str = "400px"
    responsive: bool = True
    require_auth: bool = True
    token_expiry_minutes: int = 60


class EmbeddedDashboardUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    dashboard_id: Optional[str] = None
    dashboard_config: Optional[Dict[str, Any]] = None
    embedding_mode: Optional[str] = None
    allowed_origins: Optional[List[str]] = None
    theme: Optional[str] = None
    branding: Optional[Dict[str, Any]] = None
    allow_fullscreen: Optional[bool] = None
    allow_export: Optional[bool] = None
    allow_share: Optional[bool] = None
    allow_drill_down: Optional[bool] = None
    allow_filtering: Optional[bool] = None
    auto_refresh: Optional[bool] = None
    refresh_interval_seconds: Optional[int] = None
    width: Optional[str] = None
    height: Optional[str] = None
    min_height: Optional[str] = None
    responsive: Optional[bool] = None
    require_auth: Optional[bool] = None
    token_expiry_minutes: Optional[int] = None
    is_active: Optional[bool] = None


class EmbeddedDashboardResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    dashboard_id: Optional[str]
    embedding_mode: str
    allowed_origins: List[str]
    theme: str
    branding: Optional[Dict[str, Any]]
    allow_fullscreen: bool
    allow_export: bool
    allow_share: bool
    allow_drill_down: bool
    allow_filtering: bool
    auto_refresh: bool
    refresh_interval_seconds: int
    width: str
    height: str
    min_height: str
    responsive: bool
    require_auth: bool
    token_expiry_minutes: int
    is_active: bool
    created_at: str
    updated_at: str
    created_by: Optional[str]
    embed_info: Dict[str, Any]


class BrandingConfigRequest(BaseModel):
    primary_color: str = "#6366f1"
    secondary_color: str = "#8b5cf6"
    accent_color: str = "#06b6d4"
    background_color: str = "#ffffff"
    surface_color: str = "#f8fafc"
    text_primary: str = "#1e293b"
    text_secondary: str = "#64748b"
    border_color: str = "#e2e8f0"
    success_color: str = "#10b981"
    warning_color: str = "#f59e0b"
    danger_color: str = "#ef4444"
    font_family: str = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
    font_size_base: str = "14px"
    font_weight_normal: int = 400
    font_weight_medium: int = 500
    font_weight_bold: int = 600
    logo_url: Optional[str] = None
    logo_dark_url: Optional[str] = None
    favicon_url: Optional[str] = None
    company_name: str = "VCOS"
    tagline: str = "Virtual Company Operating System"
    border_radius: str = "8px"
    border_width: str = "1px"
    shadow_intensity: str = "medium"
    animation_enabled: bool = True
    compact_mode: bool = False
    custom_css: Optional[str] = None
    show_powered_by: bool = True
    show_header: bool = True
    show_footer: bool = True
    show_export: bool = True
    show_share: bool = True
    show_fullscreen: bool = True


class SSOConfigRequest(BaseModel):
    provider: str = "jwt"
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_issuer: Optional[str] = None
    jwt_audience: Optional[str] = None
    jwt_expiry_minutes: int = 60
    saml_entity_id: Optional[str] = None
    saml_sso_url: Optional[str] = None
    saml_certificate: Optional[str] = None
    oidc_issuer: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_scopes: List[str] = ["openid", "profile", "email"]
    oauth2_authorization_url: Optional[str] = None
    oauth2_token_url: Optional[str] = None
    oauth2_userinfo_url: Optional[str] = None
    token_user_id_claim: str = "sub"
    token_email_claim: str = "email"
    token_name_claim: str = "name"
    token_roles_claim: str = "roles"
    token_org_claim: str = "org_id"
    session_cookie_name: str = "vcos_embedded_session"
    session_cookie_domain: Optional[str] = None
    session_cookie_secure: bool = True
    session_cookie_same_site: str = "lax"
    allowed_origins: List[str] = ["*"]


class EmbedTokenRequest(BaseModel):
    user_id: str
    email: str
    name: str
    org_id: str
    roles: List[str] = []
    permissions: List[str] = []
    dashboard_id: Optional[str] = None
    embedding_mode: str = "iframe"
    allowed_actions: List[str] = []
    allowed_filters: Dict[str, List[str]] = {}
    token_expiry_minutes: int = 60


class EmbedTokenResponse(BaseModel):
    token: str
    expires_in: int
    token_type: str = "Bearer"


class ValidateTokenRequest(BaseModel):
    token: str


class EmbedScriptResponse(BaseModel):
    script: str


class EmbedHTMLResponse(BaseModel):
    html: str


class EmbedInfoResponse(BaseModel):
    dashboard_id: str
    name: str
    embedding_mode: str
    embed_url_template: str
    allowed_origins: List[str]
    theme: str
    branding: Optional[Dict[str, Any]]
    features: Dict[str, bool]
    dimensions: Dict[str, Any]
    security: Dict[str, Any]


class TrackViewRequest(BaseModel):
    token: str
    metadata: Dict[str, Any] = {}


class TrackInteractionRequest(BaseModel):
    token: str
    action: str
    metadata: Dict[str, Any] = {}


class SSOConfigResponse(BaseModel):
    provider: str
    jwt_algorithm: str
    jwt_expiry_minutes: int
    allowed_origins: List[str]


class BrandingCSSResponse(BaseModel):
    css: str


class StatsResponse(BaseModel):
    total_dashboards: int
    active_dashboards: int
    embedding_modes: Dict[str, int]
    branding_configs: int
    sso_configs: int


# ==================== Dashboard Management ====================

@router.post("/dashboards", response_model=EmbeddedDashboardResponse)
async def create_embedded_dashboard(
    request: EmbeddedDashboardCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a new embedded dashboard configuration."""
    engine = get_embedded_analytics()

    dashboard = await engine.create_dashboard(
        name=request.name,
        organization_id=org.id,
        created_by=user.id,
        config=request.model_dump(),
    )

    return _to_dashboard_response(dashboard)


@router.get("/dashboards", response_model=List[EmbeddedDashboardResponse])
async def list_embedded_dashboards(
    active_only: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """List embedded dashboards."""
    engine = get_embedded_analytics()
    dashboards = await engine.list_dashboards(active_only=active_only)

    return [_to_dashboard_response(d) for d in dashboards]


@router.get("/dashboards/{dashboard_id}", response_model=EmbeddedDashboardResponse)
async def get_embedded_dashboard(
    dashboard_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get embedded dashboard configuration."""
    engine = get_embedded_analytics()
    dashboard = await engine.get_dashboard(dashboard_id)

    if not dashboard:
        raise HTTPException(404, "Embedded dashboard not found")

    return _to_dashboard_response(dashboard)


@router.patch("/dashboards/{dashboard_id}", response_model=EmbeddedDashboardResponse)
async def update_embedded_dashboard(
    dashboard_id: str,
    request: EmbeddedDashboardUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update embedded dashboard configuration."""
    engine = get_embedded_analytics()

    # Filter out None values
    updates = {k: v for k, v in request.model_dump().items() if v is not None}

    dashboard = await engine.update_dashboard(dashboard_id, updates)

    if not dashboard:
        raise HTTPException(404, "Embedded dashboard not found")

    return _to_dashboard_response(dashboard)


@router.delete("/dashboards/{dashboard_id}")
async def delete_embedded_dashboard(
    dashboard_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Delete embedded dashboard configuration."""
    engine = get_embedded_analytics()
    success = await engine.delete_dashboard(dashboard_id)

    if not success:
        raise HTTPException(404, "Embedded dashboard not found")

    return {"success": True, "message": "Embedded dashboard deleted"}


# ==================== Branding ====================

@router.post("/branding", response_model=Dict[str, str])
async def set_branding(
    request: BrandingConfigRequest,
    key: str = "default",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Set branding configuration."""
    engine = get_embedded_analytics()

    branding = BrandingConfig(**request.model_dump())
    engine.set_branding(key, branding)

    return {"success": True, "message": f"Branding config '{key}' updated"}


@router.get("/branding/{key}")
async def get_branding(
    key: str = "default",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get branding configuration."""
    engine = get_embedded_analytics()
    branding = engine.get_branding(key)

    if not branding:
        raise HTTPException(404, "Branding config not found")

    # Return as dict (excluding methods)
    return {
        "primary_color": branding.primary_color,
        "secondary_color": branding.secondary_color,
        "accent_color": branding.accent_color,
        "background_color": branding.background_color,
        "surface_color": branding.surface_color,
        "text_primary": branding.text_primary,
        "text_secondary": branding.text_secondary,
        "border_color": branding.border_color,
        "success_color": branding.success_color,
        "warning_color": branding.warning_color,
        "danger_color": branding.danger_color,
        "font_family": branding.font_family,
        "font_size_base": branding.font_size_base,
        "font_weight_normal": branding.font_weight_normal,
        "font_weight_medium": branding.font_weight_medium,
        "font_weight_bold": branding.font_weight_bold,
        "logo_url": branding.logo_url,
        "logo_dark_url": branding.logo_dark_url,
        "favicon_url": branding.favicon_url,
        "company_name": branding.company_name,
        "tagline": branding.tagline,
        "border_radius": branding.border_radius,
        "border_width": branding.border_width,
        "shadow_intensity": branding.shadow_intensity,
        "animation_enabled": branding.animation_enabled,
        "compact_mode": branding.compact_mode,
        "custom_css": branding.custom_css,
        "show_powered_by": branding.show_powered_by,
        "show_header": branding.show_header,
        "show_footer": branding.show_footer,
        "show_export": branding.show_export,
        "show_share": branding.show_share,
        "show_fullscreen": branding.show_fullscreen,
    }


@router.get("/branding/{key}/css", response_model=BrandingCSSResponse)
async def get_branding_css(
    key: str = "default",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get CSS variables for branding."""
    engine = get_embedded_analytics()
    css = engine.get_branding_css(key)
    return BrandingCSSResponse(css=css)


# ==================== SSO Configuration ====================

@router.post("/sso", response_model=Dict[str, str])
async def set_sso_config(
    request: SSOConfigRequest,
    key: str = "default",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Set SSO configuration for embedded analytics."""
    engine = get_embedded_analytics()

    sso_config = SSOConfig(
        provider=SSOProvider(request.provider),
        jwt_secret=request.jwt_secret,
        jwt_algorithm=request.jwt_algorithm,
        jwt_issuer=request.jwt_issuer,
        jwt_audience=request.jwt_audience,
        jwt_expiry_minutes=request.jwt_expiry_minutes,
        saml_entity_id=request.saml_entity_id,
        saml_sso_url=request.saml_sso_url,
        saml_certificate=request.saml_certificate,
        oidc_issuer=request.oidc_issuer,
        oidc_client_id=request.oidc_client_id,
        oidc_client_secret=request.oidc_client_secret,
        oidc_scopes=request.oidc_scopes,
        oauth2_authorization_url=request.oauth2_authorization_url,
        oauth2_token_url=request.oauth2_token_url,
        oauth2_userinfo_url=request.oauth2_userinfo_url,
        token_user_id_claim=request.token_user_id_claim,
        token_email_claim=request.token_email_claim,
        token_name_claim=request.token_name_claim,
        token_roles_claim=request.token_roles_claim,
        token_org_claim=request.token_org_claim,
        session_cookie_name=request.session_cookie_name,
        session_cookie_domain=request.session_cookie_domain,
        session_cookie_secure=request.session_cookie_secure,
        session_cookie_same_site=request.session_cookie_same_site,
        allowed_origins=request.allowed_origins,
    )

    engine.set_sso_config(key, sso_config)

    return {"success": True, "message": f"SSO config '{key}' updated"}


@router.get("/sso/{key}", response_model=SSOConfigResponse)
async def get_sso_config(
    key: str = "default",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get SSO configuration."""
    engine = get_embedded_analytics()
    sso_config = engine.get_sso_config(key)

    if not sso_config:
        raise HTTPException(404, "SSO config not found")

    return SSOConfigResponse(
        provider=sso_config.provider.value,
        jwt_algorithm=sso_config.jwt_algorithm,
        jwt_expiry_minutes=sso_config.jwt_expiry_minutes,
        allowed_origins=sso_config.allowed_origins,
    )


# ==================== Token Management ====================

@router.post("/tokens", response_model=EmbedTokenResponse)
async def create_embed_token(
    request: EmbedTokenRequest,
    sso_config_key: str = "default",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:token")),
    db: AsyncSession = Depends(get_db),
):
    """Generate JWT token for embedded analytics."""
    engine = get_embedded_analytics()

    payload = EmbedTokenPayload(
        sub=request.user_id,
        email=request.email,
        name=request.name,
        org_id=request.org_id,
        roles=request.roles,
        permissions=request.permissions,
        dashboard_id=request.dashboard_id,
        embedding_mode=request.embedding_mode,
        allowed_actions=request.allowed_actions,
        allowed_filters=request.allowed_filters,
        token_expiry_minutes=request.token_expiry_minutes,
    )

    token = engine.generate_embed_token(payload, sso_config_key)

    return EmbedTokenResponse(
        token=token,
        expires_in=request.token_expiry_minutes * 60,
        token_type="Bearer",
    )


@router.post("/tokens/validate")
async def validate_embed_token(
    request: ValidateTokenRequest,
    sso_config_key: str = "default",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Validate and decode embed token."""
    engine = get_embedded_analytics()
    payload = engine.verify_embed_token(request.token, sso_config_key)

    if not payload:
        return {"valid": False, "error": "Invalid or expired token"}

    return {
        "valid": True,
        "payload": {
            "sub": payload.sub,
            "email": payload.email,
            "name": payload.name,
            "org_id": payload.org_id,
            "roles": payload.roles,
            "permissions": payload.permissions,
            "dashboard_id": payload.dashboard_id,
            "embedding_mode": payload.embedding_mode,
            "exp": payload.exp,
            "iat": payload.iat,
            "jti": payload.jti,
        }
    }


# ==================== Embedding Generation ====================

@router.get("/dashboards/{dashboard_id}/embed-script", response_model=EmbedScriptResponse)
async def get_embed_script(
    dashboard_id: str,
    base_url: str = "",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get JavaScript SDK snippet for embedding."""
    engine = get_embedded_analytics()
    script = engine.get_embed_script(dashboard_id, base_url)
    return EmbedScriptResponse(script=script)


@router.get("/dashboards/{dashboard_id}/embed-html", response_model=EmbedHTMLResponse)
async def get_embed_html(
    dashboard_id: str,
    token: str = Query(...),
    base_url: str = "",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get HTML for iframe embedding."""
    engine = get_embedded_analytics()
    html = engine.get_embed_html(dashboard_id, token, base_url)
    return EmbedHTMLResponse(html=html)


@router.get("/dashboards/{dashboard_id}/info", response_model=EmbedInfoResponse)
async def get_embed_info(
    dashboard_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get all information needed for embedding a dashboard."""
    engine = get_embedded_analytics()
    info = engine.get_dashboard_embed_info(dashboard_id)

    if not info:
        raise HTTPException(404, "Embedded dashboard not found")

    return EmbedInfoResponse(**info)


# ==================== Embedding Security ====================

@router.options("/dashboards/{dashboard_id}/embed")
async def embed_cors_preflight(
    dashboard_id: str,
    request: Request,
    origin: str = Query(...),
):
    """Handle CORS preflight for embedding."""
    engine = get_embedded_analytics()
    headers = engine.get_cors_headers(dashboard_id, origin)

    if not headers:
        raise HTTPException(403, "Origin not allowed")

    return {"headers": headers}


@router.get("/dashboards/{dashboard_id}/csp")
async def get_csp_header(
    dashboard_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
):
    """Get Content Security Policy header for embedding."""
    engine = get_embedded_analytics()
    csp = engine.get_csp_header(dashboard_id)
    return {"content-security-policy": csp}


# ==================== Tracking ====================

@router.post("/track/view")
async def track_embed_view(
    request: TrackViewRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:track")),
    db: AsyncSession = Depends(get_db),
):
    """Track embedded dashboard view."""
    engine = get_embedded_analytics()
    event = await engine.track_embed_view(
        dashboard_id="",  # Would be extracted from token
        token=request.token,
        metadata=request.metadata,
    )
    return {"success": True, "event": event}


@router.post("/track/interaction")
async def track_embed_interaction(
    request: TrackInteractionRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:track")),
    db: AsyncSession = Depends(get_db),
):
    """Track user interaction with embedded dashboard."""
    engine = get_embedded_analytics()
    event = await engine.track_embed_interaction(
        dashboard_id="",  # Would be extracted from token
        token=request.token,
        action=request.action,
        metadata=request.metadata,
    )
    return {"success": True, "event": event}


# ==================== Statistics ====================

@router.get("/stats", response_model=StatsResponse)
async def get_embedded_analytics_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("embedded_analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get embedded analytics statistics."""
    engine = get_embedded_analytics()
    return StatsResponse(**engine.get_stats())


# ==================== Helper Functions ====================

def _to_dashboard_response(dashboard) -> EmbeddedDashboardResponse:
    """Convert dashboard to response model."""
    engine = get_embedded_analytics()
    embed_info = engine.get_dashboard_embed_info(dashboard.id) or {}

    return EmbeddedDashboardResponse(
        id=dashboard.id,
        name=dashboard.name,
        description=dashboard.description,
        dashboard_id=dashboard.dashboard_id,
        embedding_mode=dashboard.embedding_mode.value,
        allowed_origins=dashboard.allowed_origins,
        theme=dashboard.theme.value,
        branding={
            "primary_color": dashboard.branding.primary_color,
            "secondary_color": dashboard.branding.secondary_color,
            "accent_color": dashboard.branding.accent_color,
            "logo_url": dashboard.branding.logo_url,
            "company_name": dashboard.branding.company_name,
        } if dashboard.branding else None,
        allow_fullscreen=dashboard.allow_fullscreen,
        allow_export=dashboard.allow_export,
        allow_share=dashboard.allow_share,
        allow_drill_down=dashboard.allow_drill_down,
        allow_filtering=dashboard.allow_filtering,
        auto_refresh=dashboard.auto_refresh,
        refresh_interval_seconds=dashboard.refresh_interval_seconds,
        width=dashboard.width,
        height=dashboard.height,
        min_height=dashboard.min_height,
        responsive=dashboard.responsive,
        require_auth=dashboard.require_auth,
        token_expiry_minutes=dashboard.token_expiry_minutes,
        is_active=dashboard.is_active,
        created_at=dashboard.created_at.isoformat(),
        updated_at=dashboard.updated_at.isoformat(),
        created_by=dashboard.created_by,
        embed_info=embed_info,
    )


# ==================== Initialize on Module Load ====================

@router.on_event("startup")
async def startup():
    await init_embedded_analytics()