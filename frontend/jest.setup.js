const { TextEncoder, TextDecoder } = require("util");

global.TextEncoder = TextEncoder;
global.TextDecoder = TextDecoder;

// Mock next/navigation
jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: jest.fn(),
    replace: jest.fn(),
    prefetch: jest.fn(),
    back: jest.fn(),
  }),
  useSearchParams: () => ({
    get: jest.fn(),
  }),
  usePathname: () => "/",
}));

// Mock API client
jest.mock("@/lib/api", () => ({
  api: jest.fn(),
  getAdaptiveExperience: jest.fn(),
  listExternalGroups: jest.fn(),
  listGroupRoleMappings: jest.fn(),
  createGroupRoleMapping: jest.fn(),
  updateGroupRoleMapping: jest.fn(),
  deleteGroupRoleMapping: jest.fn(),
  validateGroupRoleMapping: jest.fn(),
}));

// Mock useAuth hook
jest.mock("@/hooks/useAuth", () => ({
  useAuth: () => ({
    user: {
      id: "user-1",
      email: "test@example.com",
      full_name: "Test User",
      role: "admin",
    },
    organization: { id: "org-1", name: "Test Org", slug: "test-org" },
    ready: true,
    can: (permission) => true,
    refreshProfile: jest.fn(),
    updateOrganization: jest.fn(),
  }),
}));

// Mock useFetch hook
jest.mock("@/hooks/useFetch", () => ({
  useFetch: (path) => {
    if (!path)
      return {
        data: null,
        error: null,
        loading: false,
        refetch: jest.fn(),
        refresh: jest.fn(),
      };

    const mockData = {
      "/dashboard/summary": {
        organization_name: "Test Org",
        organization_slug: "test-org",
        current_user: {
          id: "user-1",
          full_name: "Test User",
          email: "test@example.com",
          role: "admin",
        },
        total_users: 10,
        active_users: 8,
        unread_notifications: 2,
        active_sessions: 5,
        pending_invitations: 1,
        roles_count: 5,
        recent_activity: [],
        recent_notifications: [],
        workspace: {
          id: "ws-1",
          daily_goal: "",
          onboarding_completed: true,
          items: [],
        },
        learning_summary: {},
      },
      "/users": { items: [], total: 0, page: 1, page_size: 100, pages: 1 },
      "/roles": [],
      "/roles/permissions": [],
      "/users/invitations": [],
      "/organizations/me/settings": {},
      "/organizations/me/stats": {},
      "/commercial/subscription": null,
      "/commercial/invoices": [],
      "/audit": { items: [], total: 0, page: 1, page_size: 50, pages: 1 },
      "/roles/groups": [],
      "/roles/groups/test-group/mappings": [],
    };

    return {
      data: mockData[path] || null,
      error: null,
      loading: false,
      refetch: jest.fn(),
      refresh: jest.fn(),
    };
  },
}));

// Mock toast
jest.mock("@/components/ui/Toaster", () => ({
  toastError: jest.fn(),
  toastSuccess: jest.fn(),
}));

// Mock window.matchMedia
Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: jest.fn().mockImplementation((query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

// Mock ResizeObserver
global.ResizeObserver = jest.fn().mockImplementation(() => ({
  observe: jest.fn(),
  unobserve: jest.fn(),
  disconnect: jest.fn(),
}));

// Suppress console.error for cleaner test output
const originalError = console.error;
console.error = (...args) => {
  if (args[0]?.includes?.("Warning: ReactDOM.render is no longer supported"))
    return;
  if (args[0]?.includes?.("act(...)")) return;
  originalError.call(console, ...args);
};
