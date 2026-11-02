import "@testing-library/jest-dom";
import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import OnboardingContent from "./components/OnboardingContent";
import { api } from "@/lib/api";

// Mock dependencies
jest.mock("@/lib/api", () => ({
  api: jest.fn(),
  getAdaptiveExperience: jest.fn(),
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
        onboarding_completed: false,
        provisioning_state: "requested",
        provisioning_progress: 0,
        current_phase: "Identity Initialization",
        completed_steps: [],
      },
      error: null,
      loading: false,
      refetch: jest.fn(),
      refresh: jest.fn(),
    };
  },
}));

jest.mock("@/components/ui/Toaster", () => ({
  toastError: jest.fn(),
  toastSuccess: jest.fn(),
}));

// Mock localStorage
const localStorageMock = {
  getItem: jest.fn(),
  setItem: jest.fn(),
  removeItem: jest.fn(),
};
Object.defineProperty(window, "localStorage", { value: localStorageMock });

describe("OnboardingContent", () => {
  const mockApi = api as jest.MockedFunction<typeof api>;

  beforeEach(() => {
    jest.clearAllMocks();
    localStorageMock.getItem.mockReturnValue(null);
    localStorageMock.setItem.mockImplementation(() => {});
    localStorageMock.removeItem.mockImplementation(() => {});

    // Default successful API responses
    mockApi.mockImplementation((path: string, options?: any) => {
      const pathStr = typeof path === "string" ? path : path?.path;
      if (pathStr === "/users/me" && options?.method === "PATCH") {
        return Promise.resolve({});
      }
      if (pathStr === "/organizations/me" && options?.method === "PATCH") {
        return Promise.resolve({});
      }
      if (pathStr === "/users/invite" && options?.method === "POST") {
        return Promise.resolve({});
      }
      if (
        pathStr === "/onboarding/provisioning/start" &&
        options?.method === "POST"
      ) {
        return Promise.resolve({
          success: true,
          provisioning_id: "prov-123",
          message: "Provisioning started",
        });
      }
      if (pathStr === "/onboarding/provisioning/prov-123/progress") {
        return Promise.resolve({
          provisioning_id: "prov-123",
          state: "identity_initialized",
          current_step: "identity_initialization",
          current_step_name: "Identity Initialization",
          steps: [
            {
              step: "identity_initialization",
              state: "completed",
              name: "Identity Initialization",
              description: "Create organization identity and domain",
              required: true,
              recoverable: true,
              started_at: "2024-01-01T00:00:00Z",
              completed_at: "2024-01-01T00:00:10Z",
            },
            {
              step: "tenant_creation",
              state: "running",
              name: "Tenant Creation",
              description: "Create organization tenant with domain",
              required: true,
              recoverable: true,
              started_at: "2024-01-01T00:00:10Z",
            },
            {
              step: "security_initialization",
              state: "pending",
              name: "Security Initialization",
              description: "Apply security policies, MFA, encryption",
              required: true,
              recoverable: true,
            },
          ],
          current_phase: "Identity Initialization",
          provisioning_progress: 33,
          completed_count: 1,
          failed_count: 0,
          running_count: 1,
          total_steps: 15,
        });
      }
      if (pathStr === "/onboarding/status") {
        return Promise.resolve({
          onboarding_completed: false,
          provisioning_state: "requested",
          provisioning_progress: 0,
          current_phase: "Identity Initialization",
          completed_steps: [],
        });
      }
      return Promise.reject(new Error(`Unhandled API call: ${pathStr}`));
    });
  });

  it("renders welcome step initially", async () => {
    render(<OnboardingContent />);

    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
      expect(screen.getByText("Company Setup")).toBeInTheDocument();
      expect(screen.getByText("Invite Team")).toBeInTheDocument();
      expect(screen.getByText("Connect Tools")).toBeInTheDocument();
    });
  });

  it("advances to profile step when Continue is clicked", async () => {
    render(<OnboardingContent />);

    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    const continueButton = screen.getAllByText("Continue")[0];
    fireEvent.click(continueButton);

    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });
  });

  it("validates required fields in profile step", async () => {
    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Go to profile step
    fireEvent.click(screen.getAllByText("Continue")[0]);

    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    // Try to submit without required field
    const submitButton = screen.getAllByText("Continue")[0];
    fireEvent.click(submitButton);

    // Should show validation error (HTML5 validation)
    expect(screen.getByPlaceholderText("Ada Lovelace")).toHaveAttribute(
      "required",
    );
  });

  it("saves profile and advances to company step", async () => {
    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Go to profile step
    fireEvent.click(screen.getAllByText("Continue")[0]);

    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    // Fill required field
    const nameInput = screen.getByPlaceholderText("Ada Lovelace");
    fireEvent.change(nameInput, { target: { value: "Test User" } });

    // Submit
    fireEvent.click(screen.getAllByText("Continue")[0]);

    await waitFor(() => {
      expect(screen.getByText("Company Details")).toBeInTheDocument();
    });
  });

  it("advances through company, team, and integrations steps", async () => {
    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Profile step
    fireEvent.click(screen.getAllByText("Continue")[0]);

    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Ada Lovelace"), {
      target: { value: "Test User" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);

    await waitFor(() =>
      expect(screen.getByText("Company Details")).toBeInTheDocument(),
    );

    // Company step - find the Company Name input by placeholder
    fireEvent.change(screen.getByPlaceholderText("Acme Corp"), {
      target: { value: "Test Corp" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);

    await waitFor(() =>
      expect(screen.getByText("Invite Your Team")).toBeInTheDocument(),
    );

    // Team step (skip adding members) - click and wait for transition
    fireEvent.click(screen.getAllByText("Continue")[0]);

    await waitFor(() =>
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument(),
    );

    // Integrations step
    fireEvent.click(screen.getAllByText("Continue")[0]);

    await waitFor(() =>
      expect(screen.getByText("Provisioning")).toBeInTheDocument(),
    );
  });

  it("shows integration cards for all 6 providers", async () => {
    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Navigate to integrations step
    fireEvent.click(screen.getAllByText("Continue")[0]); // welcome -> profile
    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Ada Lovelace"), {
      target: { value: "Test User" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]); // profile -> company
    await waitFor(() => {
      expect(screen.getByText("Company Details")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Acme Corp"), {
      target: { value: "Test Corp" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]); // company -> team
    await waitFor(() => {
      expect(screen.getByText("Invite Your Team")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]); // team -> integrations
    await waitFor(() => {
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("GitHub")).toBeInTheDocument();
      expect(screen.getByText("Slack")).toBeInTheDocument();
      expect(screen.getByText("Google Workspace")).toBeInTheDocument();
      expect(screen.getByText("Microsoft 365 / Entra ID")).toBeInTheDocument();
      expect(screen.getByText("Okta")).toBeInTheDocument();
      expect(screen.getByText("Jira")).toBeInTheDocument();
    });
  });

  it("starts provisioning when Complete is clicked on integrations step", async () => {
    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Navigate to integrations step
    fireEvent.click(screen.getAllByText("Continue")[0]); // welcome
    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Ada Lovelace"), {
      target: { value: "Test User" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]); // profile
    await waitFor(() => {
      expect(screen.getByText("Company Details")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Acme Corp"), {
      target: { value: "Test Corp" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]); // company
    await waitFor(() => {
      expect(screen.getByText("Invite Your Team")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]); // team
    await waitFor(() => {
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]); // integrations

    await waitFor(() => {
      expect(screen.getByText("Provisioning Progress")).toBeInTheDocument();
    });

    // Should have called provisioning start API
    expect(mockApi).toHaveBeenCalledWith("/onboarding/provisioning/start", {
      method: "POST",
    });
  });

  it("displays provisioning progress with 15 steps", async () => {
    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Navigate to provisioning step
    fireEvent.click(screen.getAllByText("Continue")[0]); // welcome
    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Ada Lovelace"), {
      target: { value: "Test User" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]); // profile
    await waitFor(() => {
      expect(screen.getByText("Company Details")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Acme Corp"), {
      target: { value: "Test Corp" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]); // company
    await waitFor(() => {
      expect(screen.getByText("Invite Your Team")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]); // team
    await waitFor(() => {
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]); // integrations
    await waitFor(() => {
      expect(screen.getByText("Provisioning Progress")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getAllByText("Identity Initialization").length,
      ).toBeGreaterThan(0);
      expect(screen.getAllByText("Tenant Creation").length).toBeGreaterThan(0);
      expect(
        screen.getAllByText("Security Initialization").length,
      ).toBeGreaterThan(0);
    });
  });

  it("persists provisioning ID to localStorage for refresh recovery", async () => {
    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Navigate to provisioning step
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Ada Lovelace"), {
      target: { value: "Test User" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Company Details")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Acme Corp"), {
      target: { value: "Test Corp" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Invite Your Team")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Provisioning Progress")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(localStorageMock.setItem).toHaveBeenCalledWith(
        "vcos_onboarding_provisioning",
        expect.stringContaining("prov-123"),
      );
    });
  });

  it.skip("shows error state when provisioning fails", async () => {
    mockApi.mockImplementation((path: string, options?: any) => {
      const pathStr = typeof path === "string" ? path : path?.path;
      if (pathStr === "/users/me" && options?.method === "PATCH") {
        return Promise.resolve({});
      }
      if (pathStr === "/organizations/me" && options?.method === "PATCH") {
        return Promise.resolve({});
      }
      if (pathStr === "/users/invite" && options?.method === "POST") {
        return Promise.resolve({});
      }
      if (pathStr === "/onboarding/status") {
        return Promise.resolve({
          onboarding_completed: false,
          provisioning_state: "requested",
          provisioning_progress: 0,
          current_phase: "Identity Initialization",
          completed_steps: [],
        });
      }
      if (
        path === "/onboarding/provisioning/start" &&
        options?.method === "POST"
      ) {
        return Promise.resolve({
          success: true,
          provisioning_id: "prov-123",
          message: "Provisioning started",
        });
      }
      if (path === "/onboarding/provisioning/prov-123/progress") {
        return Promise.resolve({
          provisioning_id: "prov-123",
          state: "FAILED",
          current_step: "security_initialization",
          current_step_name: "Security Initialization",
          steps: [
            {
              step: "identity_initialization",
              state: "completed",
              name: "Identity Initialization",
              description: "Create organization identity and domain",
              required: true,
              recoverable: true,
            },
            {
              step: "tenant_creation",
              state: "completed",
              name: "Tenant Creation",
              description: "Create organization tenant with domain",
              required: true,
              recoverable: true,
            },
            {
              step: "security_initialization",
              state: "failed",
              name: "Security Initialization",
              description: "Apply security policies, MFA, encryption",
              required: true,
              recoverable: true,
              error: "MFA configuration failed",
            },
          ],
          current_phase: "Security Initialization",
          provisioning_progress: 20,
          completed_count: 2,
          failed_count: 1,
          running_count: 0,
          total_steps: 15,
          error: "MFA configuration failed",
        });
      }
      // Handle any other API calls gracefully
      return Promise.resolve({});
    });

    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Navigate to provisioning step
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Ada Lovelace"), {
      target: { value: "Test User" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Company Details")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Acme Corp"), {
      target: { value: "Test Corp" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Invite Your Team")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Provisioning Progress")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText("Failed")).toBeInTheDocument();
      expect(screen.getByText("MFA configuration failed")).toBeInTheDocument();
      expect(screen.getByText("Retry Failed Steps")).toBeInTheDocument();
    });
  });

  it("shows loading state during provisioning poll", async () => {
    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Navigate to provisioning step
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Ada Lovelace"), {
      target: { value: "Test User" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Company Details")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Acme Corp"), {
      target: { value: "Test Corp" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Invite Your Team")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Provisioning Progress")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(
        screen.getByText("Polling for updates every 5 seconds..."),
      ).toBeInTheDocument();
    });
  });

  it("navigates to complete step when provisioning reaches READY state", async () => {
    mockApi.mockImplementation((path: string, options?: any) => {
      const pathStr = typeof path === "string" ? path : path?.path;
      if (pathStr === "/users/me" && options?.method === "PATCH") {
        return Promise.resolve({});
      }
      if (pathStr === "/organizations/me" && options?.method === "PATCH") {
        return Promise.resolve({});
      }
      if (pathStr === "/users/invite" && options?.method === "POST") {
        return Promise.resolve({});
      }
      if (pathStr === "/onboarding/status") {
        return Promise.resolve({
          onboarding_completed: false,
          provisioning_state: "requested",
          provisioning_progress: 0,
          current_phase: "Identity Initialization",
          completed_steps: [],
        });
      }
      if (
        pathStr === "/onboarding/provisioning/start" &&
        options?.method === "POST"
      ) {
        return Promise.resolve({
          success: true,
          provisioning_id: "prov-123",
          message: "Provisioning started",
        });
      }
      if (pathStr === "/onboarding/provisioning/prov-123/progress") {
        return Promise.resolve({
          provisioning_id: "prov-123",
          state: "READY",
          current_step: "company_brain_initialization",
          current_step_name: "Company Brain Initialization",
          steps: Array(15)
            .fill(null)
            .map((_, i) => ({
              step: `step_${i}`,
              state: "completed",
              name: `Step ${i}`,
              description: `Description ${i}`,
              required: true,
              recoverable: true,
            })),
          current_phase: "Ready",
          provisioning_progress: 100,
          completed_count: 15,
          failed_count: 0,
          running_count: 0,
          total_steps: 15,
        });
      }
      return Promise.reject(new Error(`Unhandled API call: ${path}`));
    });

    render(<OnboardingContent />);

    // Wait for welcome step
    await waitFor(() => {
      expect(screen.getByText("Welcome to VCOS")).toBeInTheDocument();
    });

    // Navigate to provisioning step
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Your Professional Profile")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Ada Lovelace"), {
      target: { value: "Test User" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Company Details")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByPlaceholderText("Acme Corp"), {
      target: { value: "Test Corp" },
    });
    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Invite Your Team")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]);
    await waitFor(() => {
      expect(screen.getByText("Connect Your Tools")).toBeInTheDocument();
    });

    fireEvent.click(screen.getAllByText("Continue")[0]);

    // Should navigate directly to complete step since provisioning is READY
    await waitFor(() => {
      expect(
        screen.getByText(/Your VCOS workspace is ready/),
      ).toBeInTheDocument();
      expect(screen.getByText("Go to Workspace")).toBeInTheDocument();
    });
  });
});
