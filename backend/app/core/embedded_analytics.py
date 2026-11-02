"""
Embedded Analytics & White-Label BI for VCOS.

Provides:
- Embedded Analytics SDK configuration
- White-label theming and branding
- SSO/JWT authentication for embedded contexts
- Embedded dashboard/components management
- Cross-origin embedding security
"""

import hashlib
import logging
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingMode(str, Enum):
    """Embedding modes for analytics."""
    IFRAME = "iframe"           # Traditional iframe embedding
    WEB_COMPONENT = "web_component"  # Web component (custom element)
    JAVASCRIPT_SDK = "javascript_sdk"  # JavaScript SDK integration
    SERVER_SIDE = "server_side"  # Server-side rendering


class EmbeddingTheme(str, Enum):
    """Pre-built themes for embedded analytics."""
    LIGHT = "light"
    DARK = "dark"
    AUTO = "auto"  # Follows system preference
    BRANDED = "branded"  # Custom brand colors


class SSOProvider(str, Enum):
    """Supported SSO providers for embedded analytics."""
    SAML = "saml"
    OIDC = "oidc"
    OAUTH2 = "oauth2"
    JWT = "jwt"  # Custom JWT
    AZURE_AD = "azure_ad"
    GOOGLE_WORKSPACE = "google_workspace"
    OKTA = "okta"
    AUTH0 = "auth0"


@dataclass
class BrandingConfig:
    """White-label branding configuration."""
    # Colors
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

    # Typography
    font_family: str = "'Inter', -apple-system, BlinkMacSystemFont, sans-serif"
    font_size_base: str = "14px"
    font_weight_normal: int = 400
    font_weight_medium: int = 500
    font_weight_bold: int = 600

    # Logo & Branding
    logo_url: Optional[str] = None
    logo_dark_url: Optional[str] = None
    favicon_url: Optional[str] = None
    company_name: str = "VCOS"
    tagline: str = "Virtual Company Operating System"

    # UI Customization
    border_radius: str = "8px"
    border_width: str = "1px"
    shadow_intensity: str = "medium"  # none, subtle, medium, strong
    animation_enabled: bool = True
    compact_mode: bool = False

    # Custom CSS
    custom_css: Optional[str] = None

    # Feature Flags
    show_powered_by: bool = True
    show_header: bool = True
    show_footer: bool = True
    show_export: bool = True
    show_share: bool = True
    show_fullscreen: bool = True


@dataclass
class SSOConfig:
    """SSO configuration for embedded analytics."""
    provider: SSOProvider = SSOProvider.JWT

    # JWT Configuration
    jwt_secret: Optional[str] = None
    jwt_algorithm: str = "HS256"
    jwt_issuer: Optional[str] = None
    jwt_audience: Optional[str] = None
    jwt_expiry_minutes: int = 60

    # SAML Configuration
    saml_entity_id: Optional[str] = None
    saml_sso_url: Optional[str] = None
    saml_certificate: Optional[str] = None

    # OIDC Configuration
    oidc_issuer: Optional[str] = None
    oidc_client_id: Optional[str] = None
    oidc_client_secret: Optional[str] = None
    oidc_scopes: List[str] = field(default_factory=lambda: ["openid", "profile", "email"])

    # OAuth2 Configuration
    oauth2_authorization_url: Optional[str] = None
    oauth2_token_url: Optional[str] = None
    oauth2_userinfo_url: Optional[str] = None

    # Token mapping
    token_user_id_claim: str = "sub"
    token_email_claim: str = "email"
    token_name_claim: str = "name"
    token_roles_claim: str = "roles"
    token_org_claim: str = "org_id"

    # Session
    session_cookie_name: str = "vcos_embedded_session"
    session_cookie_domain: Optional[str] = None
    session_cookie_secure: bool = True
    session_cookie_same_site: str = "lax"

    # Allowed origins for embedding
    allowed_origins: List[str] = field(default_factory=list)


@dataclass
class EmbeddedDashboardConfig:
    """Configuration for an embedded dashboard."""
    id: str
    name: str
    description: Optional[str] = None

    # Embedding
    embedding_mode: EmbeddingMode = EmbeddingMode.IFRAME
    allowed_origins: List[str] = field(default_factory=list)

    # Dashboard content
    dashboard_id: Optional[str] = None
    dashboard_config: Dict[str, Any] = field(default_factory=dict)

    # UI
    theme: EmbeddingTheme = EmbeddingTheme.AUTO
    branding: Optional[BrandingConfig] = None

    # Features
    allow_fullscreen: bool = True
    allow_export: bool = True
    allow_share: bool = True
    allow_drill_down: bool = True
    allow_filtering: bool = True
    auto_refresh: bool = False
    refresh_interval_seconds: int = 300

    # Sizing
    width: str = "100%"
    height: str = "600px"
    min_height: str = "400px"
    max_height: Optional[str] = None
    responsive: bool = True

    # Security
    sso_config: Optional[SSOConfig] = None
    require_auth: bool = True
    token_expiry_minutes: int = 60

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    is_active: bool = True


@dataclass
class EmbedTokenPayload:
    """Payload for embedded analytics JWT token."""
    sub: str  # user ID
    email: str
    name: str
    org_id: str
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)

    # Embedding context
    dashboard_id: Optional[str] = None
    embedding_mode: str = "iframe"

    # UI constraints
    allowed_actions: List[str] = field(default_factory=list)
    allowed_filters: Dict[str, List[str]] = field(default_factory=dict)

    # Expiry
    exp: int = 0
    iat: int = 0
    jti: str = ""


class EmbeddedAnalyticsManager:
    """
    Manages embedded analytics configurations and tokens.

    Features:
    - Embedded dashboard management
    - White-label theming
    - SSO/JWT token generation
    - Embedding security (CORS, CSP)
    - Analytics tracking for embeds
    """

    def __init__(self):
        self._dashboards: Dict[str, EmbeddedDashboardConfig] = {}
        self._branding: Dict[str, BrandingConfig] = {}
        self._sso_configs: Dict[str, SSOConfig] = {}
        self._embed_tokens: Dict[str, EmbedTokenPayload] = {}
        self._initialized = False

    async def initialize(self):
        """Initialize embedded analytics manager."""
        if self._initialized:
            return

        # Load default branding
        self._branding["default"] = BrandingConfig()

        # Load default SSO config
        self._sso_configs["default"] = SSOConfig(
            jwt_secret=getattr(settings, 'EMBEDDED_JWT_SECRET', None),
            allowed_origins=getattr(settings, 'EMBEDDED_ALLOWED_ORIGINS', ["*"]),
        )

        self._initialized = True
        logger.info("Embedded Analytics Manager initialized")

    # ==================== Dashboard Management ====================

    async def create_dashboard(
        self,
        name: str,
        organization_id: str,
        created_by: str,
        config: Optional[Dict[str, Any]] = None,
    ) -> EmbeddedDashboardConfig:
        """Create a new embedded dashboard configuration."""
        dashboard = EmbeddedDashboardConfig(
            id=str(uuid4()),
            name=name,
            dashboard_id=config.get("dashboard_id") if config else None,
            dashboard_config=config.get("dashboard_config", {}) if config else {},
            embedding_mode=EmbeddingMode(config.get("embedding_mode", "iframe")) if config else EmbeddingMode.IFRAME,
            allowed_origins=config.get("allowed_origins", ["*"]) if config else ["*"],
            theme=EmbeddingTheme(config.get("theme", "auto")) if config else EmbeddingTheme.AUTO,
            branding=BrandingConfig(**config["branding"]) if config and config.get("branding") else None,
            allow_fullscreen=config.get("allow_fullscreen", True) if config else True,
            allow_export=config.get("allow_export", True) if config else True,
            allow_share=config.get("allow_share", True) if config else True,
            allow_drill_down=config.get("allow_drill_down", True) if config else True,
            allow_filtering=config.get("allow_filtering", True) if config else True,
            auto_refresh=config.get("auto_refresh", False) if config else False,
            refresh_interval_seconds=config.get("refresh_interval_seconds", 300) if config else 300,
            width=config.get("width", "100%") if config else "100%",
            height=config.get("height", "600px") if config else "600px",
            min_height=config.get("min_height", "400px") if config else "400px",
            responsive=config.get("responsive", True) if config else True,
            require_auth=config.get("require_auth", True) if config else True,
            token_expiry_minutes=config.get("token_expiry_minutes", 60) if config else 60,
            created_by=created_by,
        )

        self._dashboards[dashboard.id] = dashboard
        logger.info(f"Created embedded dashboard: {dashboard.id} ({name})")
        return dashboard

    async def get_dashboard(self, dashboard_id: str) -> Optional[EmbeddedDashboardConfig]:
        """Get embedded dashboard configuration."""
        return self._dashboards.get(dashboard_id)

    async def update_dashboard(
        self,
        dashboard_id: str,
        updates: Dict[str, Any],
    ) -> Optional[EmbeddedDashboardConfig]:
        """Update embedded dashboard configuration."""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return None

        # Apply updates
        for key, value in updates.items():
            if hasattr(dashboard, key):
                setattr(dashboard, key, value)

        dashboard.updated_at = datetime.utcnow()
        logger.info(f"Updated embedded dashboard: {dashboard_id}")
        return dashboard

    async def delete_dashboard(self, dashboard_id: str) -> bool:
        """Delete embedded dashboard configuration."""
        if dashboard_id in self._dashboards:
            del self._dashboards[dashboard_id]
            logger.info(f"Deleted embedded dashboard: {dashboard_id}")
            return True
        return False

    async def list_dashboards(
        self,
        organization_id: Optional[str] = None,
        active_only: bool = True,
    ) -> List[EmbeddedDashboardConfig]:
        """List embedded dashboards."""
        dashboards = list(self._dashboards.values())

        if active_only:
            dashboards = [d for d in dashboards if d.is_active]

        return dashboards

    # ==================== Branding Management ====================

    def set_branding(self, key: str, branding: BrandingConfig):
        """Set branding configuration."""
        self._branding[key] = branding
        logger.info(f"Set branding config: {key}")

    def get_branding(self, key: str = "default") -> Optional[BrandingConfig]:
        """Get branding configuration."""
        return self._branding.get(key)

    def get_branding_css(self, key: str = "default") -> str:
        """Generate CSS variables for branding."""
        branding = self.get_branding(key)
        if not branding:
            return ""

        css_vars = [
            f"--vcos-primary: {branding.primary_color};",
            f"--vcos-secondary: {branding.secondary_color};",
            f"--vcos-accent: {branding.accent_color};",
            f"--vcos-background: {branding.background_color};",
            f"--vcos-surface: {branding.surface_color};",
            f"--vcos-text-primary: {branding.text_primary};",
            f"--vcos-text-secondary: {branding.text_secondary};",
            f"--vcos-border: {branding.border_color};",
            f"--vcos-success: {branding.success_color};",
            f"--vcos-warning: {branding.warning_color};",
            f"--vcos-danger: {branding.danger_color};",
            f"--vcos-font-family: {branding.font_family};",
            f"--vcos-font-size-base: {branding.font_size_base};",
            f"--vcos-border-radius: {branding.border_radius};",
            f"--vcos-border-width: {branding.border_width};",
        ]

        if branding.custom_css:
            css_vars.append(branding.custom_css)

        return ":root {" + "\n".join(css_vars) + "}"

    # ==================== SSO / Token Management ====================

    def set_sso_config(self, key: str, config: SSOConfig):
        """Set SSO configuration."""
        self._sso_configs[key] = config
        logger.info(f"Set SSO config: {key}")

    def get_sso_config(self, key: str = "default") -> Optional[SSOConfig]:
        """Get SSO configuration."""
        return self._sso_configs.get(key)

    def generate_embed_token(
        self,
        payload: EmbedTokenPayload,
        sso_config_key: str = "default",
    ) -> str:
        """
        Generate JWT token for embedded analytics.

        Args:
            payload: Token payload with user info and embedding context
            sso_config_key: SSO configuration to use

        Returns:
            JWT token string
        """
        import jwt

        sso_config = self.get_sso_config(sso_config_key)
        if not sso_config:
            raise ValueError(f"SSO config not found: {sso_config_key}")

        secret = sso_config.jwt_secret
        if not secret:
            # Generate a temporary secret for development
            secret = getattr(settings, 'SECRET_KEY', 'dev-secret-change-in-production')

        # Set timestamps
        now = int(time.time())
        payload.iat = now
        payload.exp = now + (payload.token_expiry_minutes or 60) * 60
        payload.jti = str(uuid4())

        # Generate token
        token = jwt.encode(
            payload.__dict__,
            secret,
            algorithm=sso_config.jwt_algorithm,
        )

        logger.info(f"Generated embed token for user {payload.sub}, dashboard {payload.dashboard_id}")
        return token

    def verify_embed_token(
        self,
        token: str,
        sso_config_key: str = "default",
    ) -> Optional[EmbedTokenPayload]:
        """
        Verify and decode embed token.

        Returns:
            Decoded payload if valid, None otherwise
        """
        import jwt

        sso_config = self.get_sso_config(sso_config_key)
        if not sso_config:
            return None

        secret = sso_config.jwt_secret or getattr(settings, 'SECRET_KEY', 'dev-secret')

        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=[sso_config.jwt_algorithm],
                audience=sso_config.jwt_audience,
                issuer=sso_config.jwt_issuer,
            )

            return EmbedTokenPayload(**payload)
        except jwt.ExpiredSignatureError:
            logger.warning("Embed token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid embed token: {e}")
            return None

    # ==================== Embedding Security ====================

    def get_csp_header(self, dashboard_id: str) -> str:
        """Generate Content Security Policy header for embedding."""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return "frame-ancestors 'self';"

        origins = " ".join(dashboard.allowed_origins) if dashboard.allowed_origins else "'self'"

        return (
            f"frame-ancestors {origins}; "
            f"script-src 'self' 'unsafe-inline' 'unsafe-eval' https:; "
            f"style-src 'self' 'unsafe-inline' https:; "
            f"img-src 'self' data: https:; "
            f"font-src 'self' https:; "
            f"connect-src 'self' https: wss:; "
            f"frame-src 'self' {origins};"
        )

    def get_cors_headers(self, dashboard_id: str, origin: str) -> Dict[str, str]:
        """Get CORS headers for embedding origin."""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return {}

        # Check if origin is allowed
        allowed = False
        if "*" in dashboard.allowed_origins:
            allowed = True
        elif origin in dashboard.allowed_origins:
            allowed = True
        else:
            # Check wildcard subdomain matching
            for allowed_origin in dashboard.allowed_origins:
                if allowed_origin.startswith("*."):
                    domain = allowed_origin[2:]
                    if origin.endswith(domain):
                        allowed = True
                        break

        if not allowed:
            return {}

        return {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, Authorization, X-Embed-Token",
            "Access-Control-Allow-Credentials": "true",
            "Access-Control-Max-Age": "86400",
        }

    def get_embed_html(
        self,
        dashboard_id: str,
        token: str,
        base_url: str = "",
    ) -> str:
        """Generate HTML for iframe embedding."""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return "<html><body>Dashboard not found</body></html>"

        embed_url = f"{base_url}/embed/{dashboard_id}?token={token}"

        # Generate branding CSS
        branding_css = ""
        if dashboard.branding:
            branding_css = self.get_branding_css_for_embed(dashboard.branding)

        theme_attr = ""
        if dashboard.theme != EmbeddingTheme.AUTO:
            theme_attr = f'data-theme="{dashboard.theme.value}"'

        html = f"""<!DOCTYPE html>
<html lang="en" {theme_attr}>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{dashboard.name} - {dashboard.description or 'Embedded Analytics'}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        html, body {{
            width: 100%;
            height: 100%;
            overflow: hidden;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
        }}
        #embed-container {{
            width: 100%;
            height: 100%;
            border: none;
            background: transparent;
        }}
        {self.get_branding_css_for_embed(dashboard.branding) if dashboard.branding else ''}
    </style>
</head>
<body>
    <div id="embed-root"></div>
    <iframe
        id="embed-container"
        src="{embed_url}"
        width="100%"
        height="100%"
        frameborder="0"
        allowfullscreen
        sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
    ></iframe>
    <script>
        // Handle messages from embedded content
        window.addEventListener('message', function(event) {{
            if (event.data.type === 'vcos:resize') {{
                const iframe = document.getElementById('embed-container');
                if (iframe) {{
                    iframe.style.height = event.data.height + 'px';
                }}
            }});
            if (event.data.type === 'vcos:navigate') {{
                window.parent.postMessage({{ type: 'vcos:navigate', url: event.data.url }}, '*');
            }}
        </script>
</body>
</html>"""
        return html

    def get_branding_css_for_embed(self, branding: BrandingConfig) -> str:
        """Generate inline CSS for embedded branding."""
        return f"""
        :root {{
            --vcos-primary: {branding.primary_color};
            --vcos-secondary: {branding.secondary_color};
            --vcos-accent: {branding.accent_color};
            --vcos-background: {branding.background_color};
            --vcos-surface: {branding.surface_color};
            --vcos-text-primary: {branding.text_primary};
            --vcos-text-secondary: {branding.text_secondary};
            --vcos-border: {branding.border_color};
            --vcos-success: {branding.success_color};
            --vcos-warning: {branding.warning_color};
            --vcos-danger: {branding.danger_color};
            --vcos-font-family: {branding.font_family};
            --vcos-font-size-base: {branding.font_size_base};
            --vcos-border-radius: {branding.border_radius};
            --vcos-border-width: {branding.border_width};
        }}
        """

    # ==================== Embedding Scripts ====================

    def get_embed_script(self, dashboard_id: str, base_url: str = "") -> str:
        """Generate JavaScript SDK snippet for embedding."""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return "// Dashboard not found"

        embed_url = f"{base_url}/embed/{dashboard_id}"

        script = f"""
// VCOS Embedded Analytics SDK
(function() {{
    'use strict';

    var config = {{
        dashboardId: '{dashboard_id}',
        baseUrl: '{base_url}',
        containerId: 'vcos-embed-container',
        token: null,
        theme: '{dashboard.theme.value if dashboard.theme != EmbeddingTheme.AUTO else 'auto'}',
        width: '{dashboard.width}',
        height: '{dashboard.height}',
        responsive: {str(dashboard.responsive).lower()},
    }};

    // Create container
    function createContainer() {{
        var container = document.getElementById(config.containerId);
        if (!container) {{
            container = document.createElement('div');
            container.id = config.containerId;
            container.style.width = config.width;
            container.style.height = config.height;
            container.style.minHeight = '{dashboard.min_height}';
            if (config.responsive) {{
                container.style.maxWidth = '100%';
            }}
            document.body.appendChild(container);
        }}
        return container;
    }}

    // Load embed
    function loadEmbed(token) {{
        config.token = token;
        var container = createContainer();
        var iframe = document.createElement('iframe');
        iframe.id = 'vcos-embed-iframe';
        iframe.src = '{base_url}/embed/' + config.dashboardId + '?token=' + encodeURIComponent(token);
        iframe.width = '100%';
        iframe.height = '100%';
        iframe.style.border = 'none';
        iframe.style.minHeight = '{dashboard.min_height}';
        iframe.allowFullscreen = {str(dashboard.allow_fullscreen).lower()};
        iframe.sandbox = 'allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox';
        container.appendChild(iframe);

        // Handle resize messages
        window.addEventListener('message', function(event) {{
            if (event.data.type === 'vcos:resize') {{
                iframe.style.height = event.data.height + 'px';
            }}
        }});
    }}

    // Auto-initialize if token in URL
    var urlParams = new URLSearchParams(window.location.search);
    var token = urlParams.get('vcos_token');
    if (token) {{
        loadEmbed(token);
    }}

    // Expose SDK
    window.VCOSAnalytics = {{
        init: function(options) {{
            Object.assign(config, options);
            if (config.token) loadEmbed(config.token);
        }},
        load: loadEmbed,
        setToken: function(token) {{
            config.token = token;
            loadEmbed(token);
        }},
        destroy: function() {{
            var iframe = document.getElementById('vcos-embed-iframe');
            if (iframe) iframe.remove();
        }}
    }};
}})();
"""
        return script

    # ==================== Analytics / Tracking ====================

    async def track_embed_view(
        self,
        dashboard_id: str,
        token: str,
        metadata: Dict[str, Any] = None,
    ):
        """Track embedded dashboard view."""
        payload = EmbedTokenPayload(**self.verify_embed_token(token).__dict__) if token else None

        event = {
            "event": "embed_view",
            "dashboard_id": dashboard_id,
            "user_id": payload.sub if payload else "anonymous",
            "org_id": payload.org_id if payload else "unknown",
            "embedding_mode": payload.embedding_mode if payload else "unknown",
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        logger.info(f"Embed view tracked: {event}")
        # In production, send to analytics pipeline
        return event

    async def track_embed_interaction(
        self,
        dashboard_id: str,
        token: str,
        action: str,
        metadata: Dict[str, Any] = None,
    ):
        """Track user interaction with embedded dashboard."""
        payload = EmbedTokenPayload(**self.verify_embed_token(token).__dict__) if token else None

        event = {
            "event": "embed_interaction",
            "dashboard_id": dashboard_id,
            "user_id": payload.sub if payload else "anonymous",
            "action": action,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        logger.info(f"Embed interaction tracked: {event}")
        return event

    # ==================== Utility ====================

    def get_dashboard_embed_info(self, dashboard_id: str) -> Optional[Dict[str, Any]]:
        """Get all information needed for embedding a dashboard."""
        dashboard = self._dashboards.get(dashboard_id)
        if not dashboard:
            return None

        return {
            "dashboard_id": dashboard.id,
            "name": dashboard.name,
            "embedding_mode": dashboard.embedding_mode.value,
            "embed_url_template": f"/embed/{dashboard.id}?token={{token}}",
            "allowed_origins": dashboard.allowed_origins,
            "theme": dashboard.theme.value,
            "branding": {
                "primary_color": dashboard.branding.primary_color if dashboard.branding else None,
                "logo_url": dashboard.branding.logo_url if dashboard.branding else None,
                "company_name": dashboard.branding.company_name if dashboard.branding else "VCOS",
            } if dashboard.branding else None,
            "features": {
                "fullscreen": dashboard.allow_fullscreen,
                "export": dashboard.allow_export,
                "share": dashboard.allow_share,
                "drill_down": dashboard.allow_drill_down,
                "filtering": dashboard.allow_filtering,
            },
            "dimensions": {
                "width": dashboard.width,
                "height": dashboard.height,
                "min_height": dashboard.min_height,
                "responsive": dashboard.responsive,
            },
            "security": {
                "require_auth": dashboard.require_auth,
                "token_expiry_minutes": dashboard.token_expiry_minutes,
            },
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get embedded analytics statistics."""
        total = len(self._dashboards)
        active = sum(1 for d in self._dashboards.values() if d.is_active)

        embedding_modes = {}
        for d in self._dashboards.values():
            mode = d.embedding_mode.value
            embedding_modes[mode] = embedding_modes.get(mode, 0) + 1

        return {
            "total_dashboards": total,
            "active_dashboards": active,
            "embedding_modes": embedding_modes,
            "branding_configs": len(self._branding),
            "sso_configs": len(self._sso_configs),
        }


# Global embedded analytics manager instance
_embedded_analytics: Optional[EmbeddedAnalyticsManager] = None


def get_embedded_analytics() -> EmbeddedAnalyticsManager:
    """Get or create embedded analytics manager singleton."""
    global _embedded_analytics
    if _embedded_analytics is None:
        _embedded_analytics = EmbeddedAnalyticsManager()
    return _embedded_analytics


async def init_embedded_analytics() -> EmbeddedAnalyticsManager:
    """Initialize embedded analytics manager."""
    global _embedded_analytics
    _embedded_analytics = EmbeddedAnalyticsManager()
    await _embedded_analytics.initialize()
    return _embedded_analytics