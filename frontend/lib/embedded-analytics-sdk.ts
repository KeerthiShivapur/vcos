/**
 * VCOS Embedded Analytics SDK
 * 
 * A lightweight JavaScript SDK for embedding VCOS analytics dashboards
 * in external applications. Supports iframe, web component, and React integration.
 * 
 * @package vcos-embedded-analytics
 * @version 1.0.0
 */

// ============================================================================
// Types
// ============================================================================

export interface EmbedConfig {
  dashboardId: string;
  baseUrl?: string;
  containerId?: string;
  token?: string;
  width?: string;
  height?: string;
  theme?: 'light' | 'dark' | 'auto';
  autoResize?: boolean;
  onLoad?: () => void;
  onError?: (error: Error) => void;
  onMessage?: (data: any) => void;
}

export interface EmbedToken {
  token: string;
  expiresIn: number;
  tokenType: string;
}

export interface EmbedDashboardInfo {
  dashboardId: string;
  name: string;
  embeddingMode: string;
  embedUrlTemplate: string;
  allowedOrigins: string[];
  theme: string;
  branding: {
    primaryColor?: string;
    logoUrl?: string;
    companyName?: string;
  } | null;
  features: Record<string, boolean>;
  dimensions: {
    width: string;
    height: string;
    minHeight: string;
    responsive: boolean;
  };
  security: {
    requireAuth: boolean;
    tokenExpiryMinutes: number;
  };
}

export interface EmbeddedDashboard {
  id: string;
  name: string;
  description?: string;
  dashboardId?: string;
  embeddingMode: string;
  allowedOrigins: string[];
  theme: string;
  branding?: {
    primaryColor?: string;
    logoUrl?: string;
    companyName?: string;
  };
  features: {
    fullscreen: boolean;
    export: boolean;
    share: boolean;
    drillDown: boolean;
    filtering: boolean;
  };
  dimensions: {
    width: string;
    height: string;
    minHeight: string;
    responsive: boolean;
  };
  security: {
    requireAuth: boolean;
    tokenExpiryMinutes: number;
  };
  isActive: boolean;
  createdAt: string;
  updatedAt: string;
  embedInfo?: EmbedDashboardInfo;
}

export interface BrandingConfig {
  primaryColor: string;
  secondaryColor: string;
  accentColor: string;
  backgroundColor: string;
  surfaceColor: string;
  textPrimary: string;
  textSecondary: string;
  borderColor: string;
  successColor: string;
  warningColor: string;
  dangerColor: string;
  fontFamily: string;
  fontSizeBase: string;
  borderRadius: string;
  borderWidth: string;
  shadowIntensity: string;
  animationEnabled: boolean;
  compactMode: boolean;
  logoUrl?: string;
  logoDarkUrl?: string;
  faviconUrl?: string;
  companyName: string;
  tagline: string;
  borderRadius: string;
  borderWidth: string;
  shadowIntensity: string;
  animationEnabled: boolean;
  compactMode: boolean;
  customCss?: string;
  showPoweredBy: boolean;
  showHeader: boolean;
  showFooter: boolean;
  showExport: boolean;
  showShare: boolean;
  showFullscreen: boolean;
}

export interface SSOConfig {
  provider: string;
  jwtAlgorithm: string;
  jwtExpiryMinutes: number;
  allowedOrigins: string[];
}

export interface EmbedToken {
  token: string;
  expiresIn: number;
  tokenType: string;
}

export interface BrandingCSS {
  css: string;
}

export interface Stats {
  totalDashboards: number;
  activeDashboards: number;
  embeddingModes: Record<string, number>;
  brandingConfigs: number;
  ssoConfigs: number;
}

// ============================================================================
// Core SDK Class
// ============================================================================

export class VCOSAnalyticsSDK {
  private baseUrl: string;
  private defaultToken: string | null = null;
  private dashboardCache: Map<string, any> = new Map();
  private eventListeners: Map<string, Function[]> = new Map();

  constructor(baseUrl: string = window.location.origin) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  setDefaultToken(token: string) {
    this.defaultToken = token;
  }

  getDefaultToken(): string | null {
    return this.defaultToken;
  }

  // ==================== Dashboard Management ====================

  async listDashboards(activeOnly = true): Promise<any[]> {
    const response = await this.fetch('/dashboards', { activeOnly });
    return response.dashboards || [];
  }

  async getDashboard(dashboardId: string): Promise<any> {
    const cached = this.dashboardCache.get(dashboardId);
    if (cached) return cached;

    const response = await this.fetch(`/dashboards/${dashboardId}`);
    this.dashboardCache.set(dashboardId, response);
    return response;
  }

  async createDashboard(config: {
    name: string;
    description?: string;
    dashboardId?: string;
    embeddingMode?: 'iframe' | 'web_component' | 'javascript_sdk';
    allowedOrigins?: string[];
    theme?: 'light' | 'dark' | 'auto' | 'branded';
    branding?: Record<string, any>;
    allowFullscreen?: boolean;
    allowExport?: boolean;
    allowShare?: boolean;
    allowDrillDown?: boolean;
    allowFiltering?: boolean;
    autoRefresh?: boolean;
    refreshIntervalSeconds?: number;
    width?: string;
    height?: string;
    minHeight?: string;
    responsive?: boolean;
    requireAuth?: boolean;
    tokenExpiryMinutes?: number;
  }): Promise<any> {
    const response = await this.request('/dashboards', {
      method: 'POST',
      body: JSON.stringify(config),
    });
    return response;
  }

  async updateDashboard(dashboardId: string, updates: Record<string, any>): Promise<any> {
    const response = await this.request(`/dashboards/${dashboardId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
    this.dashboardCache.delete(dashboardId);
    return response;
  }

  async deleteDashboard(dashboardId: string): Promise<void> {
    await this.request(`/dashboards/${dashboardId}`, { method: 'DELETE' });
    this.dashboardCache.delete(dashboardId);
  }

  // ==================== Token Management ====================

  async generateToken(options: {
    userId: string;
    email: string;
    name: string;
    orgId: string;
    roles?: string[];
    permissions?: string[];
    dashboardId?: string;
    embeddingMode?: 'iframe' | 'web_component' | 'javascript_sdk';
    allowedActions?: string[];
    allowedFilters?: Record<string, string[]>;
    tokenExpiryMinutes?: number;
  }): Promise<{ token: string; expiresIn: number; tokenType: string }> {
    const response = await this.request('/tokens', {
      method: 'POST',
      body: JSON.stringify({
        user_id: options.userId,
        email: options.email,
        name: options.name,
        org_id: options.orgId,
        roles: options.roles || [],
        permissions: options.permissions || [],
        dashboard_id: options.dashboardId,
        embedding_mode: options.embeddingMode || 'iframe',
        allowed_actions: options.allowedActions || [],
        allowed_filters: options.allowedFilters || {},
        token_expiry_minutes: options.tokenExpiryMinutes || 60,
      }),
    });
    return response;
  }

  async validateToken(token: string): Promise<{ valid: boolean; payload?: any }> {
    const response = await this.request('/tokens/validate', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
    return response;
  }

  // ==================== Embedding ====================

  async getEmbedInfo(dashboardId: string): Promise<any> {
    const response = await this.fetch(`/dashboards/${dashboardId}/info`);
    return response;
  }

  async getEmbedScript(dashboardId: string, baseUrl?: string): Promise<string> {
    const response = await this.fetch(`/dashboards/${dashboardId}/embed-script?base_url=${encodeURIComponent(baseUrl || this.baseUrl)}`);
    return response.script;
  }

  async getEmbedHTML(dashboardId: string, token: string, baseUrl?: string): Promise<string> {
    const baseUrl = baseUrl || this.baseUrl;
    const response = await this.fetch(`/dashboards/${dashboardId}/embed-html?token=${encodeURIComponent(token)}&base_url=${encodeURIComponent(baseUrl)}`);
    return response.html;
  }

  generateEmbedUrl(dashboardId: string, token: string, baseUrl?: string): string {
    const base = baseUrl || this.baseUrl;
    return `${baseUrl}/embed/${dashboardId}?token=${encodeURIComponent(token)}`;
  }

  // ==================== Embedding Helpers ====================

  createIframeEmbed(dashboardId: string, token: string, options: {
    width?: string;
    height?: string;
    containerId?: string;
    baseUrl?: string;
    onLoad?: () => void;
    onError?: (error: Error) => void;
    allowFullscreen?: boolean;
  } = {}): HTMLIFrameElement {
    const {
      width = '100%',
      height = '600px',
      containerId,
      baseUrl = this.baseUrl,
      onLoad,
      onError,
      allowFullscreen = true,
    } = options;

    const token = this.defaultToken;
    if (!token) {
      throw new Error('No token available. Call setDefaultToken() or pass token in options.');
    }

    const baseUrl = options.baseUrl || this.baseUrl;
    const src = `${baseUrl}/embed/${dashboardId}?token=${encodeURIComponent(token)}`;

    const iframe = document.createElement('iframe');
    iframe.id = 'vcos-embed-iframe';
    iframe.src = src;
    iframe.width = width;
    iframe.height = height;
    iframe.style.border = 'none';
    iframe.style.minHeight = '400px';
    iframe.style.borderRadius = '0.75rem';
    iframe.allowFullscreen = true;
    iframe.sandbox = 'allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox';

    if (containerId) {
      const container = document.getElementById(containerId);
      if (container) {
        container.innerHTML = '';
        container.appendChild(iframe);
      }
    }

    iframe.onload = () => onLoad?.();
    iframe.onerror = () => onError?.(new Error('Failed to load embedded dashboard'));

    // Handle messages from embedded content
    const handleMessage = (event: MessageEvent) => {
      if (event.data.type === 'vcos:resize') {
        const iframe = document.getElementById('vcos-embed-iframe');
        if (iframe) {
          iframe.style.height = event.data.height + 'px';
        }
      }
    };
    window.addEventListener('message', handleMessage);

    // Return cleanup function
    return () => {
      window.removeEventListener('message', handleMessage);
      if (iframe.parentNode) {
        iframe.remove();
      }
    };
  }

  // ==================== Token Management ====================

  async generateToken(options: {
    dashboardId?: string;
    userId: string;
    email: string;
    name: string;
    orgId: string;
    roles?: string[];
    permissions?: string[];
    embeddingMode?: 'iframe' | 'web_component' | 'javascript_sdk';
    allowedActions?: string[];
    allowedFilters?: Record<string, string[]>;
    tokenExpiryMinutes?: number;
  }): Promise<{ token: string; expiresIn: number }> {
    const response = await this.request('/tokens', {
      method: 'POST',
      body: JSON.stringify(options),
    });
    this.defaultToken = response.token;
    return { token: response.token, expiresIn: response.expiresIn };
  }

  async validateToken(token: string): Promise<{ valid: boolean; payload?: any }> {
    const response = await this.request('/tokens/validate', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
    return response;
  }

  // ==================== Branding & Theming ====================

  async getBranding(key: string = 'default'): Promise<any> {
    return this.fetch(`/branding/${key}`);
  }

  async getBrandingCSS(key: string = 'default'): Promise<string> {
    const response = await this.fetch(`/branding/${key}/css`);
    return response.css;
  }

  applyTheme(css: string): () => void {
    const existing = document.getElementById('vcos-embedded-theme');
    if (existing) existing.remove();

    const style = document.createElement('style');
    style.id = 'vcos-embedded-theme';
    style.textContent = css;
    document.head.appendChild(style);

    return () => {
      const style = document.getElementById('vcos-embedded-theme');
      if (style) style.remove();
    };
  }

  // ==================== SSO Configuration ====================

  async getSSOConfig(key: string = 'default'): Promise<any> {
    return this.fetch(`/sso/${key}`);
  }

  async setSSOConfig(config: {
    provider: 'saml' | 'oidc' | 'oauth2' | 'jwt' | 'azure_ad' | 'google_workspace' | 'okta' | 'auth0';
    jwtSecret?: string;
    jwtAlgorithm?: string;
    jwtIssuer?: string;
    jwtAudience?: string;
    jwtExpiryMinutes?: number;
    samlEntityId?: string;
    samlSsoUrl?: string;
    samlCertificate?: string;
    oidcIssuer?: string;
    oidcClientId?: string;
    oidcClientSecret?: string;
    oidcScopes?: string[];
    oauth2AuthorizationUrl?: string;
    oauth2TokenUrl?: string;
    oauth2UserinfoUrl?: string;
    tokenUserIdClaim?: string;
    tokenEmailClaim?: string;
    tokenNameClaim?: string;
    tokenRolesClaim?: string;
    tokenOrgClaim?: string;
    sessionCookieName?: string;
    sessionCookieDomain?: string;
    sessionCookieSecure?: boolean;
    sessionCookieSameSite?: 'strict' | 'lax' | 'none';
    allowedOrigins?: string[];
  }, key: string = 'default'): Promise<void> {
    await this.request(`/sso/${key}`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  // ==================== Branding ====================

  async getBranding(key: string = 'default'): Promise<any> {
    return this.fetch(`/branding/${key}`);
  }

  async setBranding(config: {
    primaryColor?: string;
    secondaryColor?: string;
    accentColor?: string;
    backgroundColor?: string;
    surfaceColor?: string;
    textPrimary?: string;
    textSecondary?: string;
    borderColor?: string;
    successColor?: string;
    warningColor?: string;
    dangerColor?: string;
    fontFamily?: string;
    fontSizeBase?: string;
    fontWeightNormal?: number;
    fontWeightMedium?: number;
    fontWeightBold?: number;
    logoUrl?: string;
    logoDarkUrl?: string;
    faviconUrl?: string;
    companyName?: string;
    tagline?: string;
    borderRadius?: string;
    borderWidth?: string;
    shadowIntensity?: string;
    animationEnabled?: boolean;
    compactMode?: boolean;
    customCss?: string;
    showPoweredBy?: boolean;
    showHeader?: boolean;
    showFooter?: boolean;
    showExport?: boolean;
    showShare?: boolean;
    showFullscreen?: boolean;
  }, key: string = 'default'): Promise<void> {
    await this.request(`/branding/${key}`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async getBrandingCSS(key: string = 'default'): Promise<string> {
    const response = await this.fetch(`/branding/${key}/css`);
    return response.css;
  }

  // ==================== Dashboard Management ====================

  async listDashboards(activeOnly = true): Promise<any[]> {
    const response = await this.fetch('/dashboards', { activeOnly });
    return response.dashboards || [];
  }

  async getDashboard(dashboardId: string): Promise<any> {
    return this.fetch(`/dashboards/${dashboardId}`);
  }

  async createDashboard(config: {
    name: string;
    description?: string;
    dashboardId?: string;
    embeddingMode?: 'iframe' | 'web_component' | 'javascript_sdk';
    allowedOrigins?: string[];
    theme?: 'light' | 'dark' | 'auto' | 'branded';
    branding?: Record<string, any>;
    allowFullscreen?: boolean;
    allowExport?: boolean;
    allowShare?: boolean;
    allowDrillDown?: boolean;
    allowFiltering?: boolean;
    autoRefresh?: boolean;
    refreshIntervalSeconds?: number;
    width?: string;
    height?: string;
    minHeight?: string;
    responsive?: boolean;
    requireAuth?: boolean;
    tokenExpiryMinutes?: number;
  }): Promise<any> {
    return this.request('/dashboards', {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  async updateDashboard(dashboardId: string, updates: Record<string, any>): Promise<any> {
    const response = await this.request(`/dashboards/${dashboardId}`, {
      method: 'PATCH',
      body: JSON.stringify(updates),
    });
    return response;
  }

  async deleteDashboard(dashboardId: string): Promise<void> {
    await this.request(`/dashboards/${dashboardId}`, { method: 'DELETE' });
  }

  // ==================== Embedding Helpers ====================

  generateEmbedUrl(dashboardId: string, token: string): string {
    return `${this.baseUrl}/embed/${dashboardId}?token=${encodeURIComponent(token)}`;
  }

  getEmbedScript(dashboardId: string, baseUrl?: string): Promise<string> {
    return this.fetch(`/dashboards/${dashboardId}/embed-script?base_url=${encodeURIComponent(baseUrl || this.baseUrl)}`)
      .then(r => r.script);
  }

  getEmbedHTML(dashboardId: string, token: string, baseUrl?: string): Promise<string> {
    return this.fetch(`/dashboards/${dashboardId}/embed-html?token=${encodeURIComponent(token)}&base_url=${encodeURIComponent(baseUrl || this.baseUrl)}`)
      .then(r => r.html);
  }

  getEmbedInfo(dashboardId: string): Promise<any> {
    return this.fetch(`/dashboards/${dashboardId}/info`);
  }

  // ==================== Token Management ====================

  async generateToken(options: {
    userId: string;
    email: string;
    name: string;
    orgId: string;
    roles?: string[];
    permissions?: string[];
    dashboardId?: string;
    embeddingMode?: 'iframe' | 'web_component' | 'javascript_sdk';
    allowedActions?: string[];
    allowedFilters?: Record<string, string[]>;
    tokenExpiryMinutes?: number;
  }): Promise<{ token: string; expiresIn: number; tokenType: string }> {
    const response = await this.request('/tokens', {
      method: 'POST',
      body: JSON.stringify(options),
    });
    return response;
  }

  async validateToken(token: string): Promise<{ valid: boolean; payload?: any }> {
    const response = await this.request('/tokens/validate', {
      method: 'POST',
      body: JSON.stringify({ token }),
    });
    return response;
  }

  // ==================== Branding & Theming ====================

  async getBranding(key: string = 'default'): Promise<any> {
    return this.fetch(`/branding/${key}`);
  }

  async getBrandingCSS(key: string = 'default'): Promise<string> {
    const response = await this.fetch(`/branding/${key}/css`);
    return response.css;
  }

  // ==================== SSO Configuration ====================

  async getSSOConfig(key: string = 'default'): Promise<any> {
    return this.fetch(`/sso/${key}`);
  }

  async setSSOConfig(config: any, key: string = 'default'): Promise<void> {
    await this.request(`/sso/${key}`, {
      method: 'POST',
      body: JSON.stringify(config),
    });
  }

  // ==================== Statistics ====================

  async getStats(): Promise<any> {
    return this.fetch('/stats');
  }

  // ==================== Internal ====================

  private async fetch(endpoint: string, params?: Record<string, any>): Promise<any> {
    const url = new URL(`${this.baseUrl}/api/v1/embedded-analytics${endpoint}`);
    if (params) {
      Object.entries(params).forEach(([key, value]) => {
        url.searchParams.append(key, String(value));
      });
    }
    return this.request(url.toString());
  }

  private async request(url: string, options: RequestInit = {}): Promise<any> {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
      credentials: 'include',
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // ==================== Event Handling ====================

  on(event: string, listener: Function): () => void {
    if (!this.eventListeners.has(event)) {
      this.eventListeners.set(event, []);
    }
    this.eventListeners.get(event)!.push(listener);
    return () => {
      const listeners = this.eventListeners.get(event);
      if (listeners) {
        const index = listeners.indexOf(listener);
        if (index > -1) listeners.splice(index, 1);
      }
    };
  }

  emit(event: string, data: any): void {
    const listeners = this.eventListeners.get(event);
    if (listeners) {
      listeners.forEach(listener => listener(data));
    }
  }
}

// ============================================================================
// React Integration
// ============================================================================

export function createReactSDK(baseUrl?: string) {
  const sdk = new VCOSAnalyticsSDK(baseUrl);

  // React hook for easy integration
  return {
    useEmbeddedDashboard: (dashboardId: string, token: string) => {
      // This would be implemented as a React hook
      return {
        sdk,
        dashboardId,
        token,
      };
    },
    useEmbeddedAnalytics: () => {
      return {
        sdk,
        listDashboards: sdk.listDashboards.bind(sdk),
        getDashboard: sdk.getDashboard.bind(sdk),
        createDashboard: sdk.createDashboard.bind(sdk),
        updateDashboard: sdk.updateDashboard.bind(sdk),
        deleteDashboard: sdk.deleteDashboard.bind(sdk),
        generateToken: sdk.generateToken.bind(sdk),
        validateToken: sdk.validateToken.bind(sdk),
        getEmbedScript: sdk.getEmbedScript.bind(sdk),
        getEmbedHTML: sdk.getEmbedHTML.bind(sdk),
        getEmbedInfo: sdk.getEmbedInfo.bind(sdk),
        getEmbedUrl: sdk.generateEmbedUrl.bind(sdk),
        getBranding: sdk.getBranding.bind(sdk),
        setBranding: sdk.setBranding.bind(sdk),
        getSSOConfig: sdk.getSSOConfig.bind(sdk),
        setSSOConfig: sdk.setSSOConfig.bind(sdk),
        getStats: sdk.getStats.bind(sdk),
      };
    };
  };
}

// ============================================================================
// Web Component
// ============================================================================

class VCOSAnalyticsEmbed extends HTMLElement {
  private sdk: VCOSAnalyticsSDK;
  private iframe: HTMLIFrameElement | null = null;
  private token: string | null = null;

  static get observedAttributes() {
    return ['dashboard-id', 'token', 'base-url', 'width', 'height', 'theme'];
  }

  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this.sdk = new VCOSAnalyticsSDK();
  }

  connectedCallback() {
    this.render();
    this.loadEmbed();
  }

  attributeChangedCallback(name: string, oldValue: string, newValue: string) {
    if (oldValue !== newValue) {
      this.loadEmbed();
    }
  }

  private render() {
    this.shadowRoot!.innerHTML = `
      <style>
        :host { display: block; width: 100%; min-height: 400px; }
        .vcos-embed-container { width: 100%; min-height: 400px; }
        .vcos-embed-iframe { width: 100%; border: none; border-radius: 0.75rem; background: white; }
        .vcos-embed-loading { display: flex; align-items: center; justify-content: center; height: 200px; }
        .vcos-embed-error { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; padding: 20px; text-align: center; }
      </style>
      <div class="vcos-embed-container" id="embed-container"></div>
    `;
  }

  private async loadEmbed() {
    const dashboardId = this.getAttribute('dashboard-id');
    const token = this.getAttribute('token');
    const baseUrl = this.getAttribute('base-url') || window.location.origin;

    if (!dashboardId || !token) {
      this.showError('Missing dashboard-id or token attribute');
      return;
    }

    try {
      const embedUrl = `${this.baseUrl}/embed/${dashboardId}?token=${encodeURIComponent(token)}`;
      
      this.shadowRoot!.querySelector('#embed-container')!.innerHTML = `
        <iframe 
          class="vcos-embed-iframe" 
          src="${embedUrl}" 
          width="100%" 
          height="600px" 
          frameborder="0" 
          allowfullscreen
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox"
          style="width: 100%; border: none; border-radius: 0.75rem; min-height: 400px; background: white;"
        ></iframe>
      `;
    } catch (error) {
      this.showError('Failed to load embedded dashboard');
    }
  }

  private showError(message: string) {
    this.shadowRoot!.innerHTML = `
      <style>
        .vcos-embed-error { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 200px; padding: 20px; text-align: center; }
      </style>
      <div class="vcos-embed-error">
        <div class="w-16 h-16 mx-auto mb-4 rounded-full bg-red-100 flex items-center justify-center">
          <svg class="w-8 h-8 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <h3 class="text-lg font-semibold text-slate-900 mb-2">Unable to load dashboard</h3>
        <p class="text-sm text-slate-500 mb-4">${message}</p>
      </div>
    `;
  }
}

// Define custom element
if (typeof window !== 'undefined' && !customElements.get('vcos-analytics-embed')) {
  customElements.define('vcos-analytics-embed', VCOSAnalyticsEmbed);
}

// ============================================================================
// React Components (for React integration)
// ============================================================================

// These would be implemented in a React-specific package
// export const EmbeddedDashboard = ({ dashboardId, token, baseUrl, ...props }) => { ... };
// export const useEmbeddedAnalytics = () => { ... };
// export const useEmbeddedDashboard = (dashboardId: string, token: string) => { ... };
// export const usePushNotifications = () => { ... };

// ============================================================================
// Export
// ============================================================================

export default VCOSAnalyticsSDK;
export { VCOSAnalyticsSDK, VCOSAnalyticsEmbed };