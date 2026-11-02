/**
 * Company Experience Types — Universal Adaptive Experience Architecture
 *
 * These types define the company experience configuration that enables
 * VCOS to adapt its interface based on organizational complexity.
 */

export type CompanyExperienceProfile =
  | "startup" // 5-10 employees: Simple, focused, personal
  | "growing" // 11-50 employees: Teams, departments emerging
  | "mid_market" // 51-500 employees: Departments, managers, workflows
  | "large_enterprise" // 501-5000: Multi-dept, governance, regions
  | "global_enterprise"; // 5000+: Multi-entity, regions, subsidiaries

export interface CompanyExperienceConfig {
  id: string;
  organization_id: string;

  // Experience profile (determines UI complexity)
  experience_profile: CompanyExperienceProfile;

  // Company complexity indicators (used to suggest profile, not enforce)
  employee_count: number;
  organizational_depth: number; // hierarchy levels
  organizational_unit_count: number;
  legal_entity_count: number;
  geographic_footprint_count: number; // countries/regions

  // Governance complexity
  governance_complexity:
    "simple" | "standard" | "complex" | "delegated" | "federated";
  approval_levels: number;

  // Integration and workflow complexity
  integration_count: number;
  workflow_complexity: "simple" | "conditional" | "complex";

  // Experience preferences (presentation layer, not canonical state)
  enabled_modules: string[];
  default_dashboard_layout: "startup" | "growing" | "enterprise" | "custom";
  navigation_density: "comfortable" | "compact" | "dense";
  progressive_disclosure: boolean;
  show_advanced_features: boolean;

  // Localization and accessibility
  default_language: string;
  supported_languages: string[];
  timezone: string;
  date_format: string;
  number_format: string;

  // Feature flags (capability toggles)
  feature_flags: Record<string, boolean>;

  // Metadata
  configured_by?: string;
  configured_at?: string;
  last_profile_change?: string;
  previous_profile?: string;
}

export interface CompanyExperienceProfileHistory {
  id: string;
  organization_id: string;
  previous_profile: string | null;
  new_profile: string;
  changed_by: string | null;
  reason: string | null;
  metadata_json: Record<string, unknown> | null;
  created_at: string;
}

export interface CompanyExperienceProfileCapabilities {
  modules: string[];
  navigation_groups: string[];
  max_org_depth: number;
  max_departments: number;
  max_teams: number;
  governance_level: string;
  approval_levels: number;
  modules_enabled_by_default: string[];
  features?: string[];
}

export interface ProfileCapabilitiesMatrix {
  [key: string]: CompanyExperienceProfileCapabilities;
}

export interface NavigationGroup {
  key: string;
  label: string;
  items: string[];
}

export interface AdaptiveNavigationConfig {
  groups: NavigationGroup[];
  visible_modules: string[];
}

// Adaptive Experience types (new)
export interface AdaptiveModuleOut {
  key: string;
  label: string;
  icon: string;
  description: string;
  required_permissions: string[];
  priority: number;
  progressive_disclosure: boolean;
  badge_count?: number;
  badge_label?: string;
}

export interface AdaptiveNavigationGroupOut {
  key: string;
  label: string;
  modules: AdaptiveModuleOut[];
  priority: number;
  collapsible: boolean;
  default_collapsed: boolean;
}

export interface CompanyBrainInsightsOut {
  overview: Record<string, unknown>;
  recent_changes: Array<Record<string, unknown>>;
  change_count: number;
}

export interface DigitalTwinOverlayOut {
  health_score: number;
  capacity_utilization: number;
  bottlenecks: string[];
  active_scenarios: number;
}

export interface RecommendedActionOut {
  type: string;
  label: string;
  action: string;
  target: string;
  priority: number;
  source: string;
}

export interface AdaptiveExperienceOut {
  profile: CompanyExperienceProfile;
  navigation_groups: AdaptiveNavigationGroupOut[];
  visible_modules: string[];
  dashboard_layout: string;
  navigation_density: string;
  progressive_disclosure: boolean;
  show_advanced_features: boolean;
  feature_flags: Record<string, boolean>;
  company_brain_insights: CompanyBrainInsightsOut;
  digital_twin_overlay: DigitalTwinOverlayOut;
  recommended_actions: RecommendedActionOut[];
  context_fingerprint: string;
  resolved_at: string;
}

export interface ProfileTransitionPreviewOut {
  current_profile: string;
  target_profile: string;
  modules_added: string[];
  modules_removed: string[];
  navigation_groups_added: string[];
  navigation_groups_removed: string[];
  governance_level_change: {
    from: string;
    to: string;
  };
  approval_levels_change: {
    from: number;
    to: number;
  };
  new_features: string[];
}

export interface ModuleRecommendationOut {
  key: string;
  label: string;
  icon: string;
  description: string;
  required_permissions: string[];
  priority: number;
}

export interface CompanyExperienceState {
  config: CompanyExperienceConfig | null;
  profile: CompanyExperienceProfile | null;
  capabilities: CompanyExperienceProfileCapabilities | null;
  navigation: AdaptiveNavigationConfig | null;
  loading: boolean;
  error: string | null;
}

// MFA Types
export interface MFAMethod {
  id: string;
  method_type: "totp" | "passkey";
  device_name: string | null;
  device_type: string | null;
  is_primary: boolean;
  is_verified: boolean;
  verified_at: string | null;
  last_used_at: string | null;
  use_count: number;
  created_at: string;
}

export interface TOTPSetupResponse {
  method_id: string;
  provisioning_uri: string;
  secret: string;
  backup_codes: string[];
}

export interface BackupCodesResponse {
  backup_codes: string[];
}

export interface PasskeyRegistrationStartResponse {
  challenge: string;
  challenge_hash: string;
  options: Record<string, unknown>;
}

export interface PasskeyRegistrationCompleteRequest {
  credential: Record<string, unknown>;
  challenge_hash: string;
  device_name?: string;
}

export interface PasskeyAuthenticationStartResponse {
  challenge: string;
  challenge_hash: string;
  options: Record<string, unknown>;
}

export interface PasskeyAuthenticationCompleteRequest {
  credential: Record<string, unknown>;
  challenge_hash: string;
}

export interface ProfileResponse {
  suggested_profile: CompanyExperienceProfile;
  current_profile: CompanyExperienceProfile;
  organization_complexity: {
    employee_count: number;
    organizational_depth: number;
    organizational_unit_count: number;
    legal_entity_count: number;
    geographic_footprint_count: number;
    governance_complexity: string;
    workflow_complexity: string;
  };
  score_breakdown: {
    employee_score: number;
    depth_score: number;
    units_score: number;
    entities_score: number;
    geo_score: number;
    governance_score: number;
    workflow_score: number;
    total_score: number;
  };
}

export type SuggestedProfileOut = ProfileResponse;

export const EXPERIENCE_PROFILES: CompanyExperienceProfile[] = [
  "startup",
  "growing",
  "mid_market",
  "large_enterprise",
  "global_enterprise",
] as const;

export const PROFILE_LABELS: Record<CompanyExperienceProfile, string> = {
  startup: "Startup",
  growing: "Growing Company",
  mid_market: "Mid-Market",
  large_enterprise: "Large Enterprise",
  global_enterprise: "Global Enterprise",
};

export const PROFILE_DESCRIPTIONS: Record<CompanyExperienceProfile, string> = {
  startup: "Simple, focused experience for small teams (5-10 employees)",
  growing: "Growing team with departments and workflows (11-50 employees)",
  mid_market: "Multi-department organization with workflows (51-500 employees)",
  large_enterprise:
    "Complex organization with governance and regions (501-5000)",
  global_enterprise:
    "Global enterprise with subsidiaries and multi-entity support (5000+)",
};

export const PROFILE_ORDER: Record<CompanyExperienceProfile, number> = {
  startup: 0,
  growing: 1,
  mid_market: 2,
  large_enterprise: 3,
  global_enterprise: 4,
};

// Integration types
export type IntegrationKind = "webhook" | "api" | "app" | "datasource";
export type IntegrationAuthType =
  "oauth2" | "api_key" | "basic" | "saml" | "oidc";

export interface IntegrationConnection {
  id: string;
  organization_id: string;
  name: string;
  provider: string;
  kind: IntegrationKind;
  config: Record<string, unknown> | null;
  auth_type: IntegrationAuthType;
  status: "active" | "error" | "paused";
  connected_at: string | null;
  last_sync_at: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface IntegrationConnectionCreate {
  name: string;
  provider: string;
  kind?: IntegrationKind;
  config?: Record<string, unknown>;
  auth_type?: IntegrationAuthType;
}

export interface IntegrationConnectionUpdate {
  name?: string;
  config?: Record<string, unknown>;
  auth_type?: IntegrationAuthType;
  status?: "active" | "error" | "paused";
}

export interface IntegrationTestResult {
  success: boolean;
  detail: string;
}

export interface IntegrationSyncResult {
  integration_id: string;
  status: string;
  last_sync_at: string | null;
}
