"use client";

import { useState, useEffect } from "react";
import {
  Shield,
  Key,
  Users,
  AlertCircle,
  CheckCircle2,
  X,
  ChevronDown,
  ChevronUp,
  RefreshCw,
  AlertTriangle,
  Plus,
} from "lucide-react";

import { api } from "@/lib/api";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Select } from "@/components/ui/Select";
import { Input } from "@/components/ui/Input";
import { Textarea } from "@/components/ui/Textarea";
import { Modal } from "@/components/ui/Modal";
import { EmptyState } from "@/components/ui/EmptyState";
import { Spinner } from "@/components/ui/Spinner";
import { formatDate } from "@/lib/utils";
import { toastError, toastSuccess } from "@/components/ui/Toaster";

import {
  listExternalGroups,
  listGroupRoleMappings,
  createGroupRoleMapping,
  updateGroupRoleMapping,
  deleteGroupRoleMapping,
  validateGroupRoleMapping,
  ExternalGroup,
  GroupRoleMapping,
  GroupRoleMappingCreate,
  GroupRoleMappingUpdate,
} from "@/lib/api";

export function GroupRoleMappingTab() {
  const [groups, setGroups] = useState<ExternalGroup[]>([]);
  const [selectedGroup, setSelectedGroup] = useState<ExternalGroup | null>(
    null,
  );
  const [mappings, setMappings] = useState<GroupRoleMapping[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadingMappings, setLoadingMappings] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState<GroupRoleMapping | null>(
    null,
  );
  const [showValidateModal, setShowValidateModal] =
    useState<GroupRoleMapping | null>(null);
  const [newMapping, setNewMapping] = useState({
    external_group_id: "",
    role_id: "",
    justification: "",
    expires_at: "",
  });
  const [editMapping, setEditMapping] = useState({
    role_id: "",
    justification: "",
    expires_at: "",
    mapping_state: "",
  });
  const [loadingAction, setLoadingAction] = useState(false);

  const fetchGroups = async () => {
    setLoading(true);
    try {
      const data = await listExternalGroups();
      setGroups(data);
    } catch (err) {
      console.error("Failed to load groups:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMappings = async (groupId: string) => {
    setLoadingMappings(true);
    try {
      const data = await listGroupRoleMappings(groupId);
      setMappings(data);
    } catch (err) {
      console.error("Failed to load mappings:", err);
    } finally {
      setLoadingMappings(false);
    }
  };

  const handleGroupSelect = (group: ExternalGroup) => {
    setSelectedGroup(group);
    fetchMappings(group.id);
  };

  const handleCreateMapping = async () => {
    if (!newMapping.external_group_id || !newMapping.role_id) return;
    setLoadingAction(true);
    try {
      const mapping = await createGroupRoleMapping(
        newMapping.external_group_id,
        newMapping,
      );
      toastSuccess("Group role mapping created");
      setShowCreateModal(false);
      setNewMapping({
        external_group_id: "",
        role_id: "",
        justification: "",
        expires_at: "",
      });
      if (selectedGroup) fetchMappings(selectedGroup.id);
    } catch (err) {
      toastError(
        "Failed to create mapping",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoadingAction(false);
    }
  };

  const handleEditMapping = async (mapping: GroupRoleMapping) => {
    if (!editMapping.role_id) return;
    setLoadingAction(true);
    try {
      await updateGroupRoleMapping(
        mapping.external_group_id,
        mapping.id,
        editMapping,
      );
      toastSuccess("Mapping updated");
      setShowEditModal(null);
      setEditMapping({
        role_id: "",
        justification: "",
        expires_at: "",
        mapping_state: "",
      });
      if (selectedGroup) fetchMappings(selectedGroup.id);
    } catch (err) {
      toastError(
        "Failed to update mapping",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoadingAction(false);
    }
  };

  const handleValidateMapping = async (mapping: GroupRoleMapping) => {
    setLoadingAction(true);
    try {
      await validateGroupRoleMapping(mapping.external_group_id, mapping.id);
      toastSuccess("Mapping validated");
      setShowValidateModal(null);
      if (selectedGroup) fetchMappings(selectedGroup.id);
    } catch (err) {
      toastError(
        "Failed to validate mapping",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoadingAction(false);
    }
  };

  const handleDeleteMapping = async (mapping: GroupRoleMapping) => {
    if (
      !confirm(
        `Revoke mapping for group "${mapping.external_group_name}" and role "${mapping.role_name}"?`,
      )
    )
      return;
    setLoadingAction(true);
    try {
      await deleteGroupRoleMapping(mapping.external_group_id, mapping.id);
      toastSuccess("Mapping revoked");
      if (selectedGroup) fetchMappings(selectedGroup.id);
    } catch (err) {
      toastError(
        "Failed to revoke mapping",
        err instanceof Error ? err.message : undefined,
      );
    } finally {
      setLoadingAction(false);
    }
  };

  const handleOpenCreateModal = (group: ExternalGroup) => {
    setNewMapping({ ...newMapping, external_group_id: group.id });
    setShowCreateModal(true);
  };

  const handleOpenEditModal = (mapping: GroupRoleMapping) => {
    setEditMapping({
      role_id: mapping.role_id,
      justification: mapping.justification || "",
      expires_at: mapping.expires_at ? mapping.expires_at.split("T")[0] : "",
      mapping_state: mapping.mapping_state,
    });
    setShowEditModal(mapping);
  };

  const handleOpenValidateModal = (mapping: GroupRoleMapping) => {
    setShowValidateModal(mapping);
  };

  const getStateBadge = (state: string) => {
    switch (state) {
      case "active":
        return <Badge tone="success">Active</Badge>;
      case "pending":
        return <Badge tone="warning">Pending Validation</Badge>;
      case "revoked":
        return <Badge tone="danger">Revoked</Badge>;
      case "expired":
        return <Badge tone="danger">Expired</Badge>;
      case "conflict":
        return <Badge tone="danger">Conflict</Badge>;
      default:
        return <Badge tone="neutral">{state}</Badge>;
    }
  };

  const getSyncStatusBadge = (status: string) => {
    switch (status) {
      case "synced":
        return <Badge tone="success">Synced</Badge>;
      case "pending":
        return <Badge tone="warning">Pending</Badge>;
      case "error":
        return <Badge tone="danger">Error</Badge>;
      default:
        return <Badge tone="neutral">{status}</Badge>;
    }
  };

  useEffect(() => {
    fetchGroups();
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink">Group-to-Role Mapping</h1>
          <p className="text-muted mt-1">
            Map external identity provider groups to VCOS roles with governance
            controls
          </p>
        </div>
        <Button onClick={fetchGroups} disabled={loading}>
          <RefreshCw
            className={`h-4 w-4 mr-2 ${loading ? "animate-spin" : ""}`}
          />{" "}
          Refresh
        </Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-10">
          <Spinner />
        </div>
      ) : groups.length === 0 ? (
        <Card>
          <EmptyState
            icon={Users}
            title="No external groups found"
            description="Connect an identity provider (Microsoft 365, Okta, etc.) to sync groups, then map them to VCOS roles."
          />
        </Card>
      ) : (
        <div className="grid gap-6 lg:grid-cols-3">
          {/* Group List */}
          <Card className="lg:col-span-1">
            <h3 className="border-b border-line px-5 py-4 text-sm font-semibold text-ink">
              External Groups
            </h3>
            <div className="p-3 space-y-2 max-h-[600px] overflow-y-auto">
              {groups.map((group) => (
                <button
                  key={group.id}
                  onClick={() => handleGroupSelect(group)}
                  className={`w-full text-left p-3 rounded-lg border transition-colors ${selectedGroup?.id === group.id ? "border-brand/50 bg-brand/5" : "border-line hover:border-brand/30"}`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${group.sync_status === "synced" ? "bg-success/10 text-success" : group.sync_status === "error" ? "bg-danger/10 text-danger" : "bg-muted text-muted"}`}
                    >
                      <Users className="h-5 w-5" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-ink truncate">
                        {group.display_name}
                      </p>
                      <p className="text-[12px] text-muted truncate">
                        {group.identity_provider_name} · {group.members_count}{" "}
                        members
                      </p>
                    </div>
                    {getSyncStatusBadge(group.sync_status)}
                  </div>
                </button>
              ))}
            </div>
          </Card>

          {/* Group Role Mappings */}
          <Card className="lg:col-span-2">
            {selectedGroup ? (
              <>
                <div className="flex items-center justify-between border-b border-line px-5 py-4">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-brand/10 text-brand">
                      <Users className="h-5 w-5" />
                    </div>
                    <div>
                      <h3 className="text-sm font-semibold text-ink">
                        {selectedGroup.display_name}
                      </h3>
                      <p className="text-[12px] text-muted">
                        {selectedGroup.identity_provider_name} ·{" "}
                        {selectedGroup.members_count} members
                      </p>
                    </div>
                  </div>
                  <Button
                    variant="secondary"
                    onClick={() => handleOpenCreateModal(selectedGroup)}
                  >
                    <Plus className="h-4 w-4 mr-2" /> Map Role
                  </Button>
                </div>
                <div className="p-5">
                  {loadingMappings ? (
                    <div className="flex justify-center py-10">
                      <Spinner />
                    </div>
                  ) : mappings.length === 0 ? (
                    <EmptyState
                      icon={Shield}
                      title="No role mappings"
                      description="Map this group to a VCOS role to grant its members the corresponding permissions."
                    />
                  ) : (
                    <div className="space-y-3">
                      {mappings.map((mapping) => (
                        <div
                          key={mapping.id}
                          className="flex items-center justify-between p-4 border border-line rounded-lg bg-canvas/50"
                        >
                          <div className="flex items-center gap-3 min-w-0 flex-1">
                            <div
                              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-lg ${mapping.mapping_state === "active" ? "bg-success/10 text-success" : mapping.mapping_state === "pending" ? "bg-warning/10 text-warning" : "bg-muted text-muted"}`}
                            >
                              <Shield className="h-5 w-5" />
                            </div>
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <p className="font-medium text-ink truncate">
                                  {mapping.role_name}
                                </p>
                                <Badge tone="neutral" className="text-[10px]">
                                  {mapping.role_code}
                                </Badge>
                              </div>
                              <p className="text-[12px] text-muted truncate">
                                Mapped by{" "}
                                {mapping.mapped_by_name || mapping.mapped_by} ·{" "}
                                {formatDate(mapping.created_at)}
                              </p>
                              {mapping.justification && (
                                <p className="text-[11px] text-muted truncate mt-1">
                                  {mapping.justification}
                                </p>
                              )}
                            </div>
                          </div>
                          <div className="flex items-center gap-2">
                            {getStateBadge(mapping.mapping_state)}
                            {mapping.tenant_verified && (
                              <Badge tone="success" className="text-[10px]">
                                Tenant Verified
                              </Badge>
                            )}
                            {mapping.group_verified && (
                              <Badge tone="success" className="text-[10px]">
                                Group Verified
                              </Badge>
                            )}
                            {mapping.expires_at && (
                              <Badge tone="warning" className="text-[10px]">
                                Expires{" "}
                                {formatDate(mapping.expires_at).split("T")[0]}
                              </Badge>
                            )}
                            <div className="flex items-center gap-1">
                              {mapping.mapping_state === "pending" && (
                                <Button
                                  variant="secondary"
                                  size="sm"
                                  onClick={() =>
                                    handleOpenValidateModal(mapping)
                                  }
                                  disabled={loadingAction}
                                >
                                  <CheckCircle2 className="h-3 w-3 mr-1" />{" "}
                                  Validate
                                </Button>
                              )}
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleOpenEditModal(mapping)}
                                disabled={loadingAction}
                              >
                                <ChevronDown className="h-3 w-3" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteMapping(mapping)}
                                disabled={loadingAction}
                              >
                                <X className="h-3 w-3" />
                              </Button>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div className="text-center py-10">
                <Shield className="mx-auto h-12 w-12 text-muted" />
                <h3 className="mt-4 font-medium text-ink">Select a group</h3>
                <p className="mt-2 text-muted">
                  Choose an external group from the left to view and manage its
                  role mappings.
                </p>
              </div>
            )}
          </Card>
        </div>
      )}

      {/* Create Mapping Modal */}
      <Modal
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        title="Create Role Mapping"
        footer={
          <div className="flex justify-end gap-2">
            <Button
              variant="secondary"
              onClick={() => setShowCreateModal(false)}
            >
              Cancel
            </Button>
            <Button
              onClick={handleCreateMapping}
              loading={loadingAction}
              disabled={!newMapping.external_group_id || !newMapping.role_id}
            >
              Create Mapping
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <Select
            label="External Group"
            value={newMapping.external_group_id}
            onChange={(e) =>
              setNewMapping({
                ...newMapping,
                external_group_id: e.target.value,
              })
            }
            options={groups.map((g) => ({
              value: g.id,
              label: `${g.display_name} (${g.identity_provider_name})`,
            }))}
            required
          />
          <Select
            label="VCOS Role"
            value={newMapping.role_id}
            onChange={(e) =>
              setNewMapping({ ...newMapping, role_id: e.target.value })
            }
            options={[
              { value: "ceo", label: "CEO" },
              { value: "admin", label: "Admin" },
              { value: "manager", label: "Manager" },
              { value: "hr", label: "HR" },
              { value: "finance", label: "Finance" },
              { value: "developer", label: "Developer" },
              { value: "employee", label: "Employee" },
            ]}
            required
          />
          <Textarea
            label="Justification (required)"
            value={newMapping.justification}
            onChange={(e) =>
              setNewMapping({ ...newMapping, justification: e.target.value })
            }
            placeholder="Business justification for this mapping..."
            required
            rows={3}
          />
          <Input
            label="Expires At (optional)"
            type="date"
            value={newMapping.expires_at}
            onChange={(e) =>
              setNewMapping({ ...newMapping, expires_at: e.target.value })
            }
          />
          <p className="text-sm text-muted">
            This mapping will require admin validation before becoming active.
            The external group must be verified as belonging to your
            organization&apos;s tenant.
          </p>
        </div>
      </Modal>

      {/* Edit Mapping Modal */}
      {showEditModal && (
        <Modal
          open={true}
          onClose={() => setShowEditModal(null)}
          title="Edit Role Mapping"
          footer={
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => setShowEditModal(null)}
              >
                Cancel
              </Button>
              <Button
                onClick={() => handleEditMapping(showEditModal!)}
                loading={loadingAction}
                disabled={!editMapping.role_id}
              >
                Save Changes
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <Select
              label="VCOS Role"
              value={editMapping.role_id}
              onChange={(e) =>
                setEditMapping({ ...editMapping, role_id: e.target.value })
              }
              options={[
                { value: "ceo", label: "CEO" },
                { value: "admin", label: "Admin" },
                { value: "manager", label: "Manager" },
                { value: "hr", label: "HR" },
                { value: "finance", label: "Finance" },
                { value: "developer", label: "Developer" },
                { value: "employee", label: "Employee" },
              ]}
              required
            />
            <Textarea
              label="Justification"
              value={editMapping.justification}
              onChange={(e) =>
                setEditMapping({
                  ...editMapping,
                  justification: e.target.value,
                })
              }
              rows={3}
            />
            <Input
              label="Expires At (optional)"
              type="date"
              value={editMapping.expires_at}
              onChange={(e) =>
                setEditMapping({ ...editMapping, expires_at: e.target.value })
              }
            />
            <Select
              label="Mapping State"
              value={editMapping.mapping_state}
              onChange={(e) =>
                setEditMapping({
                  ...editMapping,
                  mapping_state: e.target.value,
                })
              }
              options={[
                { value: "pending", label: "Pending Validation" },
                { value: "active", label: "Active" },
                { value: "revoked", label: "Revoked" },
                { value: "expired", label: "Expired" },
                { value: "conflict", label: "Conflict" },
              ]}
            />
          </div>
        </Modal>
      )}

      {/* Validate Mapping Modal */}
      {showValidateModal && (
        <Modal
          open={true}
          onClose={() => setShowValidateModal(null)}
          title="Validate Group Role Mapping"
          footer={
            <div className="flex justify-end gap-2">
              <Button
                variant="secondary"
                onClick={() => setShowValidateModal(null)}
              >
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => handleValidateMapping(showValidateModal!)}
                loading={loadingAction}
              >
                <CheckCircle2 className="h-4 w-4 mr-2" /> Confirm Validation
              </Button>
            </div>
          }
        >
          <div className="space-y-4">
            <AlertTriangle className="mx-auto h-12 w-12 text-warning" />
            <div className="text-center">
              <p className="font-medium text-ink">
                Validate this group-to-role mapping?
              </p>
              <p className="mt-2 text-sm text-muted">
                This will mark the mapping as active and verify that the
                external group belongs to your organization&apos;s tenant. This
                action requires administrative privileges.
              </p>
            </div>
            <div className="p-4 bg-canvas/50 rounded-lg">
              <p className="font-medium text-ink">
                Group: {showValidateModal.external_group_name}
              </p>
              <p className="text-sm text-muted">
                Role: {showValidateModal.role_name} (
                {showValidateModal.role_code})
              </p>
              <p className="text-sm text-muted">
                Mapped by:{" "}
                {showValidateModal.mapped_by_name ||
                  showValidateModal.mapped_by}
              </p>
              <p className="text-sm text-muted">
                Justification:{" "}
                {showValidateModal.justification || "None provided"}
              </p>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}
