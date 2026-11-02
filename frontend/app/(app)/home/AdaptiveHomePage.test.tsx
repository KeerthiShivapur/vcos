import "@testing-library/jest-dom";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { AdaptiveHomePage } from "./AdaptiveHomePage";
import { getAdaptiveExperience } from "@/lib/api";

jest.mock("@/lib/api", () => ({
  getAdaptiveExperience: jest.fn(),
  api: jest.fn(),
}));

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
    can: (permission: string) => true,
    refreshProfile: jest.fn(),
    updateOrganization: jest.fn(),
  }),
}));

jest.mock("@/hooks/useFetch", () => ({
  useFetch: (path: string | null) => {
    if (!path)
      return {
        data: null,
        error: null,
        loading: false,
        refetch: jest.fn(),
        refresh: jest.fn(),
      };
    return {
      data: {
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
      error: null,
      loading: false,
      refetch: jest.fn(),
      refresh: jest.fn(),
    };
  },
}));

// Mock router for navigation tests
const mockPush = jest.fn();
const mockReplace = jest.fn();
const mockPrefetch = jest.fn();
const mockBack = jest.fn();

jest.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: mockReplace,
    prefetch: mockPrefetch,
    back: mockBack,
  }),
}));

const mockGetAdaptiveExperience = getAdaptiveExperience as jest.MockedFunction<
  typeof getAdaptiveExperience
>;

const createMockAdaptiveExperience = (overrides = {}) => ({
  profile: "startup",
  navigation_groups: [
    {
      key: "workspace",
      label: "Workspace",
      modules: [
        {
          key: "home",
          label: "Home",
          icon: "Home",
          description: "Personal landing page",
          required_permissions: [],
          priority: 100,
          progressive_disclosure: false,
          badge_count: 0,
        },
        {
          key: "workspace",
          label: "Workspace",
          icon: "LayoutGrid",
          description: "Unified operating surface",
          required_permissions: [],
          priority: 95,
          progressive_disclosure: false,
          badge_count: 0,
        },
        {
          key: "my-work",
          label: "My Work",
          icon: "ListTodo",
          description: "Tasks and commitments assigned to you",
          required_permissions: [],
          priority: 90,
          progressive_disclosure: false,
          badge_count: 2,
          badge_label: "open",
        },
        {
          key: "my-day",
          label: "My Day",
          icon: "Sun",
          description: "Daily operating surface",
          required_permissions: [],
          priority: 90,
          progressive_disclosure: false,
          badge_count: 0,
        },
        {
          key: "notifications",
          label: "Notifications",
          icon: "Bell",
          description: "Your notifications",
          required_permissions: [],
          priority: 85,
          progressive_disclosure: false,
          badge_count: 0,
        },
      ],
      priority: 100,
      collapsible: false,
      default_collapsed: false,
    },
    {
      key: "ai",
      label: "AI",
      modules: [
        {
          key: "ai",
          label: "AI Companion",
          icon: "Sparkles",
          description: "Conversational AI for work",
          required_permissions: [],
          priority: 95,
          progressive_disclosure: false,
          badge_count: 0,
        },
      ],
      priority: 95,
      collapsible: true,
      default_collapsed: false,
    },
  ],
  visible_modules: [
    "home",
    "workspace",
    "my-work",
    "my-day",
    "ai",
    "notifications",
  ],
  dashboard_layout: "startup",
  navigation_density: "comfortable",
  progressive_disclosure: true,
  show_advanced_features: false,
  feature_flags: { ai_companion_enabled: true },
  company_brain_insights: {
    overview: {},
    recent_changes: [
      {
        title: "New pattern discovered",
        type: "pattern",
        description: "Task completion pattern",
        occurred_at: "2024-01-01T10:00:00Z",
      },
    ],
    change_count: 1,
  },
  digital_twin_overlay: {
    health_score: 0.85,
    capacity_utilization: 0.65,
    bottlenecks: ["Task queue backup"],
    active_scenarios: 2,
  },
  recommended_actions: [
    {
      type: "create_task",
      label: "Create your first task",
      action: "/tasks/new",
      target: "tasks",
      priority: 1,
      source: "system",
    },
    {
      type: "invite_member",
      label: "Invite team members",
      action: "/settings?tab=members",
      target: "settings",
      priority: 2,
      source: "system",
    },
  ],
  context_fingerprint: "abc123",
  resolved_at: new Date().toISOString(),
  ...overrides,
});

describe("AdaptiveHomePage", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockGetAdaptiveExperience.mockResolvedValue(createMockAdaptiveExperience());
  });

  it("shows loading skeleton initially", () => {
    mockGetAdaptiveExperience.mockImplementation(() => new Promise(() => {}));

    render(<AdaptiveHomePage />);

    // Check for skeleton loader (animate-pulse class on skeleton elements)
    const skeletonElements = document.querySelectorAll(".animate-pulse");
    expect(skeletonElements.length).toBeGreaterThan(0);
  }, 15000);

  it("renders profile header with organization name and profile badge", async () => {
    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        // Use container.querySelector to avoid screen issues
        const testOrg = container.querySelector("h1");
        const startup = container.querySelector(".badge");
        const desc = container.querySelector("p.mt-1.text-sm.text-muted");

        expect(testOrg).toBeInTheDocument();
        expect(testOrg?.textContent).toContain("Test Org");
        expect(startup).toBeInTheDocument();
        expect(startup?.textContent).toContain("Startup");
        expect(desc).toBeInTheDocument();
        expect(desc?.textContent).toContain(
          "Focused workspace for small teams",
        );
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("renders dashboard stats", async () => {
    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("Total Users");
        expect(container.textContent).toContain("10");
        expect(container.textContent).toContain("Active Users");
        expect(container.textContent).toContain("8");
        expect(container.textContent).toContain("Pending Invitations");
        expect(container.textContent).toContain("1");
        expect(container.textContent).toContain("Active Sessions");
        expect(container.textContent).toContain("5");
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("renders workspace navigation groups and modules", async () => {
    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("Workspace");
        expect(container.textContent).toContain("Home");
        expect(container.textContent).toContain("My Work");
        expect(container.textContent).toContain("My Day");
        expect(container.textContent).toContain("AI");
        expect(container.textContent).toContain("AI Companion");
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("shows module badge counts", async () => {
    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("unread");
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("renders quick actions", async () => {
    render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(screen.getByText("Recommended for You")).toBeInTheDocument();
        expect(screen.getByText("Create your first task")).toBeInTheDocument();
        expect(screen.getByText("Invite team members")).toBeInTheDocument();
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("renders Company Brain insights", async () => {
    render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(screen.getByText("Company Brain")).toBeInTheDocument();
        expect(screen.getByText("1 changes")).toBeInTheDocument();
        expect(screen.getByText("New pattern discovered")).toBeInTheDocument();
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("renders Digital Twin overlay", async () => {
    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("Digital Twin");
        expect(container.textContent).toContain("85%");
        expect(container.textContent).toContain("65%");
        expect(container.textContent).toContain("Task queue backup");
        expect(container.textContent).toContain("2 running");
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("renders sidebar with profile info", async () => {
    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("Experience Profile");
        expect(container.textContent).toContain("Startup");
        expect(container.textContent).toContain("Layoutstartup");
        expect(container.textContent).toContain("Navigationcomfortable");
        expect(container.textContent).toContain("Advanced FeaturesDisabled");
        expect(container.textContent).toContain("Progressive DisclosureOn");
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("renders visible modules quick access in sidebar", async () => {
    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("Available Modules");
        expect(container.textContent).toContain("Home");
        expect(container.textContent).toContain("Workspace");
        expect(container.textContent).toContain("My Work");
        expect(container.textContent).toContain("My Day");
        expect(container.textContent).toContain("AI Companion");
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("renders feature flags", async () => {
    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("Feature Flags");
        expect(container.textContent).toContain("ai companion enabledOn");
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("shows Configure Experience button", async () => {
    render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(screen.getByText("Configure Experience")).toBeInTheDocument();
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("handles different profiles correctly", async () => {
    mockGetAdaptiveExperience.mockResolvedValue(
      createMockAdaptiveExperience({ profile: "growing" }),
    );

    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("Growing");
        expect(container.textContent).toContain(
          "Expanded operational visibility",
        );
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("shows enterprise profile with correct badge", async () => {
    mockGetAdaptiveExperience.mockResolvedValue(
      createMockAdaptiveExperience({ profile: "large_enterprise" }),
    );

    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.textContent).toContain("Large Enterprise");
        expect(container.textContent).toContain(
          "Governed enterprise operations",
        );
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("handles API error gracefully", async () => {
    mockGetAdaptiveExperience.mockRejectedValue(
      new Error("Failed to load experience"),
    );

    const { container } = render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(container.querySelector("h3")).toHaveTextContent(
          "Could not load adaptive experience",
        );
        expect(container.querySelector("p.max-w-sm")).toHaveTextContent(
          "Failed to load experience",
        );
        expect(container.querySelector("button")).toHaveTextContent(
          "Try again",
        );
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("shows empty state when no experience data", async () => {
    mockGetAdaptiveExperience.mockResolvedValue(null);

    render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(
          screen.getByText("No experience configuration"),
        ).toBeInTheDocument();
        expect(
          screen.getByText(
            "Your company's adaptive experience is being initialized.",
          ),
        ).toBeInTheDocument();
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("refresh button triggers reload", async () => {
    render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(screen.getByText("Refresh")).toBeInTheDocument();
      },
      { timeout: 15000 },
    );

    const refreshButton = screen.getByText("Refresh");
    fireEvent.click(refreshButton);

    await waitFor(
      () => {
        expect(mockGetAdaptiveExperience).toHaveBeenCalledTimes(2);
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("navigates to module when module card is clicked", async () => {
    mockPush.mockClear();
    mockReplace.mockClear();
    mockPrefetch.mockClear();
    mockBack.mockClear();

    render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        const myWorkElements = screen.getAllByText("My Work");
        expect(myWorkElements.length).toBeGreaterThanOrEqual(1);
      },
      { timeout: 15000 },
    );

    fireEvent.click(screen.getAllByText("My Work")[0]);

    expect(mockPush).toHaveBeenCalledWith("/my-work");
  }, 15000);

  it("displays Digital Twin bottlenecks when present", async () => {
    mockGetAdaptiveExperience.mockResolvedValue(
      createMockAdaptiveExperience({
        digital_twin_overlay: {
          health_score: 0.75,
          capacity_utilization: 0.9,
          bottlenecks: ["High task queue", "Memory pressure", "CPU saturation"],
          active_scenarios: 5,
        },
      }),
    );

    render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(screen.getByText("High task queue")).toBeInTheDocument();
        expect(screen.getByText("Memory pressure")).toBeInTheDocument();
        expect(screen.getByText("CPU saturation")).toBeInTheDocument();
      },
      { timeout: 15000 },
    );
  }, 15000);

  it("does not show Digital Twin section when no data", async () => {
    mockGetAdaptiveExperience.mockResolvedValue(
      createMockAdaptiveExperience({
        digital_twin_overlay: {
          health_score: 0,
          capacity_utilization: 0,
          bottlenecks: [],
          active_scenarios: 0,
        },
        company_brain_insights: {
          overview: {},
          recent_changes: [],
          change_count: 0,
        },
      }),
    );

    render(<AdaptiveHomePage />);

    await waitFor(
      () => {
        expect(screen.queryByText("Digital Twin")).not.toBeInTheDocument();
        expect(screen.queryByText("Company Brain")).not.toBeInTheDocument();
      },
      { timeout: 15000 },
    );
  }, 15000);
});
