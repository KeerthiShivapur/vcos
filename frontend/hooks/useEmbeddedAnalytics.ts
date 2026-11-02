"use client";

import { useCallback, useEffect, useState } from "react";
import { useAuth } from "@/hooks/useAuth";

interface EmbeddedDashboardConfig {
  id: string;
  name: string;
  description?: string;
  embedding_mode: "iframe" | "web_component" | "javascript_sdk";
  allowed_origins: string[];
  theme: "light" | "dark" | "auto" | "branded";
  branding?: {
    primary_color?: string;
    logo_url?: string;
    company_name?: string;
  };
  features: {
    fullscreen: boolean;
    export: boolean;
    share: boolean;
    drill_down: boolean;
    filtering: boolean;
  };
  dimensions: {
    width: string;
    height: string;
    min_height: string;
    responsive: boolean;
  };
  security: {
    require_auth: boolean;
    token_expiry_minutes: number;
  };
}

interface EmbedTokenPayload {
  sub: string;
  email: string;
  name: string;
  org_id: string;
  roles: string[];
  permissions: string[];
  dashboard_id?: string;
  embedding_mode: string;
  allowed_actions: string[];
  allowed_filters: Record<string, string[]>;
  exp: number;
  iat: number;
  jti: string;
}

interface EmbedInfoResponse {
  dashboard_id: string;
  name: string;
  embedding_mode: string;
  embed_url_template: string;
  allowed_origins: string[];
  theme: string;
  branding: {
    primary_color?: string;
    logo_url?: string;
    company_name?: string;
  } | null;
  features: Record<string, boolean>;
  dimensions: {
    width: string;
    height: string;
    min_height: string;
    responsive: boolean;
  };
  security: {
    require_auth: boolean;
    token_expiry_minutes: number;
  };
}

interface EmbedScriptResponse {
  script: string;
}

interface EmbedHTMLResponse {
  html: string;
}

interface EmbedTokenResponse {
  token: string;
  expires_in: number;
  token_type: string;
}

interface EmbedScriptResponse {
  script: string;
}

interface UseEmbeddedAnalyticsReturn {
  // State
  isLoading: boolean;
  error: string | null;
  dashboard: EmbeddedDashboardConfig | null;
  embedInfo: EmbedInfoResponse | null;
  embedScript: string | null;
  embedHTML: string | null;
  token: string | null;

  // Actions
  fetchDashboard: (dashboardId: string) => Promise<void>;
  fetchEmbedInfo: (dashboardId: string) => Promise<void>;
  generateToken: (dashboardId?: string, options?: TokenOptions) => Promise<string>;
  validateToken: (token: string) => Promise<boolean>;
  getEmbedScript: (dashboardId: string, baseUrl?: string) => Promise<string>;
  getEmbedHTML: (dashboardId: string, token: string, baseUrl?: string) => Promise<string>;
  trackView: (token: string, metadata?: Record<string, any>) => Promise<void>;
  trackInteraction: (token: string, action: string, metadata?: Record<string, any>) => Promise<void>;
}

interface TokenOptions {
  dashboardId?: string;
  embeddingMode?: "iframe" | "web_component" | "javascript_sdk";
  allowedActions?: string[];
  allowedFilters?: Record<string, string[]>;
  tokenExpiryMinutes?: number;
}

export function useEmbeddedAnalytics(): UseEmbeddedAnalyticsReturn {
  const { user, accessToken } = useAuth();

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<any>(null);
  const [embedInfo, setEmbedInfo] = useState<any>(null);
  const [embedScript, setEmbedScript] = useState<string | null>(null);
  const [embedHTML, setEmbedHTML] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);

  const apiCall = useCallback(async (endpoint: string, options: RequestInit = {}) => {
    const response = await fetch(`/api/v1/embedded-analytics${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: "Request failed" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }, [accessToken]);

  const fetchDashboard = useCallback(async (dashboardId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiCall(`/dashboards/${dashboardId}`);
      setDashboard(data);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch dashboard");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [apiCall]);

  const fetchEmbedInfo = useCallback(async (dashboardId: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await apiCall(`/dashboards/${dashboardId}/info`);
      setEmbedInfo(data);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch embed info");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [apiCall]);

  const generateToken = useCallback(async (options: TokenOptions = {}) => {
    setIsLoading(true);
    setError(null);
    try {
      const { user } = useAuth();
      if (!user) throw new Error("User not authenticated");

      const response = await apiCall("/tokens", {
        method: "POST",
        body: JSON.stringify({
          user_id: user.id,
          email: user.email,
          name: user.fullName || user.email,
          org_id: user.organizationId || "",
          roles: [user.role || "member"],
          permissions: [],
          dashboard_id: options.dashboardId,
          embedding_mode: options.embeddingMode || "iframe",
          allowed_actions: options.allowedActions || [],
          allowed_filters: options.allowedFilters || {},
          token_expiry_minutes: options.tokenExpiryMinutes || 60,
        }),
      });

      setToken(response.token);
      return response.token;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate token");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [apiCall]);

  const validateToken = useCallback(async (token: string): Promise<boolean> => {
    try {
      await fetch("/api/v1/embedded-analytics/tokens/validate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ token }),
      });
      return true;
    } catch {
      return false;
    }
  }, [accessToken]);

  const getEmbedScript = useCallback(async (dashboardId: string, baseUrl?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const baseUrl = baseUrl || window.location.origin;
      const data = await apiCall(`/dashboards/${dashboardId}/embed-script?base_url=${encodeURIComponent(baseUrl)}`);
      setEmbedScript(data.script);
      return data.script;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get embed script");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [apiCall]);

  const getEmbedHTML = useCallback(async (dashboardId: string, token: string, baseUrl?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const baseUrl = baseUrl || window.location.origin;
      const data = await apiCall(`/dashboards/${dashboardId}/embed-html?token=${encodeURIComponent(token)}&base_url=${encodeURIComponent(baseUrl)}`);
      setEmbedHTML(data.html);
      return data.html;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to get embed HTML");
      throw err;
    } finally {
      setIsLoading(false);
    }
  }, [apiCall]);

  const trackView = useCallback(async (token: string, metadata?: Record<string, any>) => {
    try {
      await fetch("/api/v1/embedded-analytics/track/view", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ token, metadata }),
      });
    } catch (err) {
      console.error("Track view failed:", err);
    }
  }, [accessToken]);

  const trackInteraction = useCallback(async (token: string, action: string, metadata?: Record<string, any>) => {
    try {
      await fetch("/api/v1/embedded-analytics/track/interaction", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ token, action, metadata }),
      });
    } catch (err) {
      console.error("Track interaction failed:", err);
    }
  }, [accessToken]);

  return {
    isLoading,
    error,
    dashboard,
    embedInfo,
    embedScript,
    embedHTML,
    token,
    fetchDashboard,
    fetchEmbedInfo,
    generateToken,
    validateToken,
    getEmbedScript,
    getEmbedHTML,
    trackView,
    trackInteraction,
  };
}

// Hook for white-label theming
export function useWhiteLabelTheme(brandingKey: string = "default") {
  const [css, setCss] = useState<string>("");

  useEffect(() => {
    const fetchCSS = async () => {
      try {
        const response = await fetch(`/api/v1/embedded-analytics/branding/${brandingKey}/css`, {
          headers: { Authorization: `Bearer ${accessToken}` },
        });
        if (response.ok) {
          const data = await response.json();
          setCss(data.css);
        }
      } catch (err) {
        console.error("Failed to load branding CSS:", err);
      }
    };

    fetchCSS();
  }, [brandingKey]);

  const applyTheme = useCallback(() => {
    if (css) {
      const style = document.createElement("style");
      style.id = "vcos-embedded-theme";
      style.textContent = css;
      document.head.appendChild(style);
      return () => style.remove();
    }
  }, [css]);

  useEffect(() => {
    const cleanup = applyTheme();
    return cleanup;
  }, [applyTheme]);

  return { css, applyTheme };
}

// Hook for SSO integration
export function useEmbeddedSSO() {
  const { accessToken } = useAuth();

  const getSSOConfig = useCallback(async (key: string = "default") => {
    const response = await fetch(`/api/v1/embedded-analytics/sso/${key}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    return response.json();
  }, [accessToken]);

  const setSSOConfig = useCallback(async (config: any, key: string = "default") => {
    const response = await fetch(`/api/v1/embedded-analytics/sso/${key}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(config),
    });
    return response.json();
  }, [accessToken]);

  return { getSSOConfig, setSSOConfig };
}

// Hook for branding
export function useEmbeddedBranding(brandingKey: string = "default") {
  const { accessToken } = useAuth();

  const getBranding = useCallback(async (key: string = "default") => {
    const response = await fetch(`/api/v1/embedded-analytics/branding/${key}`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    return response.json();
  }, [accessToken]);

  const setBranding = useCallback(async (config: any, key: string = "default") => {
    const response = await fetch(`/api/v1/embedded-analytics/branding/${key}`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(config),
    });
    return response.json();
  }, [accessToken]);

  const getBrandingCSS = useCallback(async (key: string = "default") => {
    const response = await fetch(`/api/v1/embedded-analytics/branding/${key}/css`, {
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    const data = await response.json();
    return data.css;
  }, [accessToken]);

  return { getBranding, setBranding, getBrandingCSS };
}

// Utility functions for embedding
export function generateEmbedUrl(dashboardId: string, token: string, baseUrl: string = window.location.origin): string {
  return `${baseUrl}/embed/${dashboardId}?token=${encodeURIComponent(token)}`;
}

export function generateEmbedScript(dashboardId: string, baseUrlParam: string, options: {
  containerId?: string;
  width?: string;
  height?: string;
  token?: string;
} = {}): string {
  const { containerId = "vcos-embed-container", width = "100%", height = "600px", token } = options;
  const baseUrl = baseUrlParam || window.location.origin;

  return `
// VCOS Embedded Analytics SDK
(function() {
  'use strict';

  var config = {
    dashboardId: '${dashboardId}',
    baseUrl: '${baseUrl}',
    containerId: '${options.containerId}',
    token: '${options.token || ""}',
    width: '${options.width}',
    height: '${options.height}',
  };

  function loadEmbed(token) {
    const container = document.getElementById(config.containerId);
    if (!container) return;

    const iframe = document.createElement('iframe');
    iframe.id = 'vcos-embed-iframe';
    iframe.src = config.baseUrl + '/embed/' + config.dashboardId + '?token=' + encodeURIComponent(token);
    iframe.width = '100%';
    iframe.height = '100%';
    iframe.style.border = 'none';
    iframe.style.minHeight = '400px';
    iframe.allowFullscreen = true;
    iframe.sandbox = 'allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox';
    container.appendChild(iframe);

    window.addEventListener('message', function(event) {
      if (event.data.type === 'vcos:resize') {
        iframe.style.height = event.data.height + 'px';
      }
    });
  }

  window.VCOSAnalytics = {
    init: function(options) {
      if (options.token) loadEmbed(options.token);
    },
    load: function(token) { loadEmbed(token); },
    setToken: function(token) { loadEmbed(token); },
    destroy: function() {
      const iframe = document.getElementById('vcos-embed-iframe');
      if (iframe) iframe.remove();
    }
  };

  // Auto-init if token in URL
  var urlParams = new URLSearchParams(window.location.search);
  var token = urlParams.get('vcos_token');
  if (token) loadEmbed(token);
})();
`;
}