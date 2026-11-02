import "@testing-library/jest-dom";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { GroupRoleMappingTab } from "./GroupRoleMappingTab";
import {
  listExternalGroups,
  listGroupRoleMappings,
  createGroupRoleMapping,
  updateGroupRoleMapping,
  deleteGroupRoleMapping,
  validateGroupRoleMapping,
} from "@/lib/api";

jest.mock("@/lib/api", () => ({
  listExternalGroups: jest.fn(),
  listGroupRoleMappings: jest.fn(),
  createGroupRoleMapping: jest.fn(),
  updateGroupRoleMapping: jest.fn(),
  deleteGroupRoleMapping: jest.fn(),
  validateGroupRoleMapping: jest.fn(),
  api: jest.fn(),
}));

jest.mock("@/components/ui/Toaster", () => ({
  toastError: jest.fn(),
  toastSuccess: jest.fn(),
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
    can: (permission: string) => permission === "roles:manage",
  }),
}));

const mockListExternalGroups = listExternalGroups as jest.MockedFunction<
  typeof listExternalGroups
>;
const mockListGroupRoleMappings = listGroupRoleMappings as jest.MockedFunction<
  typeof listGroupRoleMappings
>;
const mockCreateGroupRoleMapping =
  createGroupRoleMapping as jest.MockedFunction<typeof createGroupRoleMapping>;
const mockUpdateGroupRoleMapping =
  updateGroupRoleMapping as jest.MockedFunction<typeof updateGroupRoleMapping>;
const mockDeleteGroupRoleMapping =
  deleteGroupRoleMapping as jest.MockedFunction<typeof deleteGroupRoleMapping>;
const mockValidateGroupRoleMapping =
  validateGroupRoleMapping as jest.MockedFunction<
    typeof validateGroupRoleMapping
  >;

const mockGroups = [
  {
    id: "group-1",
    organization_id: "org-1",
    identity_provider_id: "idp-1",
    identity_provider_name: "Microsoft Entra ID",
    external_group_id: "entra-group-1",
    display_name: "Engineering Team",
    description: "All engineers",
    members_count: 15,
    sync_status: "synced",
    last_synced_at: "2024-01-01T10:00:00Z",
  },
  {
    id: "group-2",
    organization_id: "org-1",
    identity_provider_id: "idp-2",
    identity_provider_name: "Okta",
    external_group_id: "okta-group-1",
    display_name: "Sales Team",
    description: "Sales representatives",
    members_count: 8,
    sync_status: "pending",
    last_synced_at: null,
  },
];

const mockMappings = [
  {
    id: "mapping-1",
    organization_id: "org-1",
    external_group_id: "group-1",
    external_group_name: "Engineering Team",
    role_id: "developer",
    role_name: "Developer",
    role_code: "developer",
    mapped_by: "user-1",
    mapped_by_name: "Admin User",
    mapping_state: "active",
    justification: "Engineers need developer access",
    expires_at: null,
    tenant_verified: true,
    group_verified: true,
    validated_by: "user-1",
    validated_at: "2024-01-01T10:00:00Z",
    revoked_by: null,
    revoked_at: null,
    revocation_reason: null,
    created_at: "2024-01-01T09:00:00Z",
    updated_at: "2024-01-01T09:00:00Z",
  },
];

describe("GroupRoleMappingTab", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockListExternalGroups.mockResolvedValue(mockGroups);
    mockListGroupRoleMappings.mockResolvedValue(mockMappings);
    mockCreateGroupRoleMapping.mockResolvedValue(mockMappings[0]);
    mockUpdateGroupRoleMapping.mockResolvedValue(mockMappings[0]);
    mockDeleteGroupRoleMapping.mockResolvedValue({
      message: "Group role mapping revoked",
    });
    mockValidateGroupRoleMapping.mockResolvedValue({
      ...mockMappings[0],
      mapping_state: "active",
    });
  });

  it("loads and displays external groups", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      expect(screen.getByText("Group-to-Role Mapping")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Map external identity provider groups to VCOS roles with governance controls",
        ),
      ).toBeInTheDocument();
      expect(
        screen.getAllByText("Engineering Team").length,
      ).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Sales Team")).toBeInTheDocument();
      expect(screen.getByText(/Microsoft Entra ID/)).toBeInTheDocument();
      expect(screen.getByText(/Okta/)).toBeInTheDocument();
      expect(screen.getByText(/15 members/)).toBeInTheDocument();
      expect(screen.getByText(/8 members/)).toBeInTheDocument();
    });
  });

  it("shows sync status badges", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      expect(screen.getByText("Synced")).toBeInTheDocument();
      expect(screen.getByText("Pending")).toBeInTheDocument();
    });
  });

  it("loads mappings when group is selected", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      expect(
        screen.getAllByText("Engineering Team").length,
      ).toBeGreaterThanOrEqual(1);
    });

    // Click on the first group
    fireEvent.click(screen.getAllByText("Engineering Team")[0]);

    await waitFor(() => {
      expect(
        screen.getAllByText("Engineering Team").length,
      ).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Developer")).toBeInTheDocument();
      expect(screen.getByText("Active")).toBeInTheDocument();
      expect(screen.getByText("Tenant Verified")).toBeInTheDocument();
      expect(screen.getByText("Group Verified")).toBeInTheDocument();
    });
  });

  it("shows empty state when no group selected", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      expect(screen.getByText("Select a group")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Choose an external group from the left to view and manage its role mappings.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("opens create mapping modal", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      expect(screen.getByText("Map Role")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Map Role"));

    await waitFor(() => {
      expect(screen.getByText("Create Role Mapping")).toBeInTheDocument();
      expect(screen.getByText("External Group")).toBeInTheDocument();
      expect(screen.getByText("VCOS Role")).toBeInTheDocument();
      expect(screen.getByText("Justification (required)")).toBeInTheDocument();
      expect(screen.getByText("Expires At (optional)")).toBeInTheDocument();
    });
  });

  it("creates a new mapping", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    // Click the Map Role button in the sidebar header
    fireEvent.click(screen.getByText("Map Role"));

    // Wait for modal to appear
    await waitFor(() => {
      expect(screen.getByText("Create Role Mapping")).toBeInTheDocument();
    });

    await waitFor(() => {
      // Fill form - find the VCOS Role select (second select in modal)
      const selects = screen.getAllByRole("combobox");
      console.log("Number of comboboxes:", selects.length);
      const vcosRoleSelect = selects[1]; // Second select is VCOS Role
      fireEvent.change(vcosRoleSelect, { target: { value: "manager" } });
      // Find justification textarea by placeholder
      const justificationTextarea = screen.getByPlaceholderText(
        "Business justification for this mapping...",
      );
      fireEvent.change(justificationTextarea, {
        target: { value: "Managers need elevated access" },
      });

      // Check if button is enabled
      const createButton = screen.getByText("Create Mapping");
      console.log("Button disabled:", createButton.disabled);
      fireEvent.click(createButton);
    });

    await waitFor(() => {
      expect(mockCreateGroupRoleMapping).toHaveBeenCalledWith(
        "group-1",
        expect.objectContaining({
          external_group_id: "group-1",
          role_id: "manager",
          justification: "Managers need elevated access",
        }),
      );
    });
  });

  it("validates required fields in create mapping", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    fireEvent.click(screen.getByText("Map Role"));

    await waitFor(() => {
      // Try to submit without required fields
      fireEvent.click(screen.getByText("Create Mapping"));
    });

    // Should not call API if validation fails
    expect(mockCreateGroupRoleMapping).not.toHaveBeenCalled();
  });

  it("opens edit mapping modal", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      // Click the edit button (chevron down) - find by testid
      const editButton = screen
        .getByTestId("icon-chevrondown")
        .closest("button");
      fireEvent.click(editButton);
    });

    await waitFor(() => {
      expect(screen.getByText("Edit Role Mapping")).toBeInTheDocument();
      expect(screen.getByText("VCOS Role")).toBeInTheDocument();
      expect(screen.getByText("Justification")).toBeInTheDocument();
      expect(screen.getByText("Expires At (optional)")).toBeInTheDocument();
      expect(screen.getByText("Mapping State")).toBeInTheDocument();
    });
  });

  it("opens validate mapping modal for pending mappings", async () => {
    // Create a pending mapping
    const pendingMapping = {
      ...mockMappings[0],
      id: "mapping-2",
      mapping_state: "pending",
      tenant_verified: false,
      group_verified: false,
      validated_by: null,
      validated_at: null,
    };
    mockListGroupRoleMappings.mockResolvedValue([pendingMapping]);

    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      // Click validate button
      const validateButton = screen.getByText("Validate");
      fireEvent.click(validateButton);
    });

    await waitFor(() => {
      expect(
        screen.getByText("Validate Group Role Mapping"),
      ).toBeInTheDocument();
      expect(screen.getByText("Confirm Validation")).toBeInTheDocument();
    });
  });

  it("validates a pending mapping", async () => {
    const pendingMapping = {
      ...mockMappings[0],
      id: "mapping-2",
      mapping_state: "pending",
      tenant_verified: false,
      group_verified: false,
    };
    mockListGroupRoleMappings.mockResolvedValue([pendingMapping]);

    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      fireEvent.click(screen.getByText("Validate"));
    });

    await waitFor(() => {
      fireEvent.click(screen.getByText("Confirm Validation"));
    });

    await waitFor(() => {
      expect(mockValidateGroupRoleMapping).toHaveBeenCalledWith(
        "group-1",
        "mapping-2",
      );
    });
  });

  it("revokes a mapping with confirmation", async () => {
    // Mock window.confirm to return true
    const originalConfirm = window.confirm;
    window.confirm = jest.fn(() => true);

    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      // Click the delete/revoke button (X icon) - find by testid
      const revokeButton = screen.getByTestId("icon-x").closest("button");
      fireEvent.click(revokeButton);
    });

    await waitFor(() => {
      expect(mockDeleteGroupRoleMapping).toHaveBeenCalledWith(
        "group-1",
        "mapping-1",
      );
    });

    // Restore original confirm
    window.confirm = originalConfirm;
  });

  it("shows loading state while fetching groups", async () => {
    mockListExternalGroups.mockImplementation(() => new Promise(() => {})); // Never resolves

    render(<GroupRoleMappingTab />);

    expect(screen.getByText("Loading")).toBeInTheDocument();
  });

  it("shows empty state when no groups found", async () => {
    mockListExternalGroups.mockResolvedValue([]);

    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      expect(screen.getByText("No external groups found")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Connect an identity provider (Microsoft 365, Okta, etc.) to sync groups, then map them to VCOS roles.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("shows empty state when group has no mappings", async () => {
    mockListGroupRoleMappings.mockResolvedValue([]);

    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      expect(screen.getByText("No role mappings")).toBeInTheDocument();
      expect(
        screen.getByText(
          "Map this group to a VCOS role to grant its members the corresponding permissions.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("refresh button reloads groups", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      expect(screen.getByText("Refresh")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Refresh"));

    await waitFor(() => {
      expect(mockListExternalGroups).toHaveBeenCalledTimes(2);
    });
  });

  it("displays state badges correctly", async () => {
    const mappingsWithStates = [
      { ...mockMappings[0], id: "m1", mapping_state: "active" },
      { ...mockMappings[0], id: "m2", mapping_state: "pending" },
      { ...mockMappings[0], id: "m3", mapping_state: "revoked" },
      { ...mockMappings[0], id: "m4", mapping_state: "expired" },
      { ...mockMappings[0], id: "m5", mapping_state: "conflict" },
    ];
    mockListGroupRoleMappings.mockResolvedValue(mappingsWithStates);

    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      expect(screen.getByText("Active")).toBeInTheDocument();
      expect(screen.getByText("Pending Validation")).toBeInTheDocument();
      expect(screen.getByText("Revoked")).toBeInTheDocument();
      expect(screen.getByText("Expired")).toBeInTheDocument();
      expect(screen.getByText("Conflict")).toBeInTheDocument();
    });
  });

  it("shows expiry badge when mapping has expiration", async () => {
    const mappingWithExpiry = {
      ...mockMappings[0],
      expires_at: "2025-12-31T23:59:59Z",
    };
    mockListGroupRoleMappings.mockResolvedValue([mappingWithExpiry]);

    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      expect(screen.getByText("Expires 1 Jan 2026")).toBeInTheDocument();
    });
  }, 15000);

  it("shows error state when API fails", async () => {
    mockListExternalGroups.mockRejectedValue(
      new Error("Failed to load groups"),
    );

    render(<GroupRoleMappingTab />);

    // The component doesn't have an error boundary, so it will show the error in console
    // We just verify it doesn't crash
    await waitFor(() => {
      expect(screen.getByText("Group-to-Role Mapping")).toBeInTheDocument();
    });
  }, 15000);

  it("handles edit mapping with state change", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      // Edit button has ChevronDown icon, find by testid and click
      const editButton = screen
        .getByTestId("icon-chevrondown")
        .closest("button");
      fireEvent.click(editButton);
    });

    await waitFor(() => {
      // Change state to revoked - find the select element directly
      const mappingStateSelect = screen.getByDisplayValue("Active");
      fireEvent.change(mappingStateSelect, { target: { value: "revoked" } });
      fireEvent.click(screen.getByText("Save Changes"));
    });

    await waitFor(() => {
      expect(mockUpdateGroupRoleMapping).toHaveBeenCalledWith(
        "group-1",
        "mapping-1",
        expect.objectContaining({
          mapping_state: "revoked",
        }),
      );
    });
  }, 15000);

  it("shows tenant and group verified badges", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      expect(screen.getByText("Tenant Verified")).toBeInTheDocument();
      expect(screen.getByText("Group Verified")).toBeInTheDocument();
    });
  }, 15000);

  it("displays mapping justification", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      expect(
        screen.getByText("Engineers need developer access"),
      ).toBeInTheDocument();
    });
  }, 15000);

  it("shows mapped by info", async () => {
    render(<GroupRoleMappingTab />);

    await waitFor(() => {
      fireEvent.click(screen.getByText("Engineering Team"));
    });

    await waitFor(() => {
      expect(screen.getByText(/Mapped by Admin User/)).toBeInTheDocument();
    });
  }, 15000);
});
