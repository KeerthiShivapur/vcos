"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import {
  Calendar,
  Clock,
  Users,
  Video,
  Mic,
  Settings,
  Plus,
  X,
  ChevronDown,
  ChevronUp,
  MoreHorizontal,
  Trash2,
  Edit,
  Play,
  Pause,
  Square,
  Share,
  ExternalLink,
  MessageSquare,
  LayoutGrid,
  BarChart2,
  AlertTriangle,
  CheckCircle,
  XCircle,
  HelpCircle,
  Info,
  AlertCircle,
  Star,
  Flag,
  Bookmark,
  Tag,
  Link as LinkIcon,
  Hash,
  Key,
  Lock,
  Unlock,
  Shield,
  Eye,
  EyeOff,
  Volume2,
  VolumeX,
  Mic as MicIcon,
  MicOff,
  UserPlus,
  FileText,
  Camera,
  CameraOff,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { Table, TableHeader, TableBody, TableRow, TableCell, TableHead } from "@/components/ui/Table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import { Textarea } from "@/components/ui/Textarea";
import { Select } from "@/components/ui/Select";
import { Switch } from "@/components/ui/Switch";
import { Label } from "@/components/ui/Label";
import { cn } from "@/lib/utils";

const MEETING_TYPE_LABELS = {
  team: "Team",
  board: "Board",
  client: "Client",
  one_on_one: "1:1",
  all_hands: "All Hands",
};

const SCALE_LABELS = {
  small: "Small",
  medium: "Medium",
  large: "Large",
  enterprise: "Enterprise",
};

export default function NewMeetingPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  interface FormData {
    title: string;
    description: string;
    meeting_type: string;
    scale: string;
    status: string;
    scheduled_start: string;
    scheduled_end: string;
    timezone: string;
    project_id: string;
    participant_ids: string[];
    settings: Record<string, any>;
    materials: any[];
    wait_room_enabled: boolean;
    chat_enabled: boolean;
    reactions_enabled: boolean;
    screen_share_enabled: boolean;
    require_approval: boolean;
    allow_external_guests: boolean;
    password_protected: boolean;
    password: string;
  }

  const [formData, setFormData] = useState<FormData>({
    title: "",
    description: "",
    meeting_type: "team",
    scale: "small",
    status: "scheduled",
    scheduled_start: "",
    scheduled_end: "",
    timezone: "UTC",
    project_id: "",
    participant_ids: [],
    settings: {},
    materials: [],
    wait_room_enabled: true,
    chat_enabled: true,
    reactions_enabled: true,
    screen_share_enabled: true,
    require_approval: false,
    allow_external_guests: true,
    password_protected: false,
    password: "",
  });
  const [newAgendaItem, setNewAgendaItem] = useState("");
  const [agendaItems, setAgendaItems] = useState<Array<{ id: string; title: string; description: string; duration_minutes: number; order: number }>>([]);
  const [showInviteModal, setShowInviteModal] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    if (type === "checkbox") {
      setFormData(prev => ({ ...prev, [name]: (e.target as HTMLInputElement).checked }));
    } else {
      setFormData(prev => ({ ...prev, [name]: value }));
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.title.trim()) {
      setError("Title is required");
      return;
    }
    setLoading(true);
    try {
      // await createMeeting(formData);
      router.push("/app/meetings");
    } catch (error) {
      setError(error instanceof Error ? error.message : "Failed to create meeting");
    } finally {
      setLoading(false);
    }
  };

  const addAgendaItem = () => {
    if (!newAgendaItem.trim()) return;
    setAgendaItems(prev => [...prev, {
      id: Date.now().toString(),
      title: newAgendaItem,
      description: "",
      duration_minutes: 15,
      order: Date.now(),
    }]);
    setNewAgendaItem("");
  };

  const removeAgendaItem = (id: string) => {
    setAgendaItems(prev => prev.filter(item => item.id !== id));
  };

  const removeParticipant = (index: number) => {
    setFormData(prev => ({
      ...prev,
      participant_ids: prev.participant_ids.filter((_, i) => i !== index)
    }));
  };

  const addParticipant = () => {
    // In a real app, this would open a user picker modal
    setFormData(prev => ({
      ...prev,
      participant_ids: [...prev.participant_ids, `user_${Date.now()}`]
    }));
  };

  const removeParticipantById = (id: string) => {
    setFormData(prev => ({
      ...prev,
      participant_ids: prev.participant_ids.filter(pid => pid !== id)
    }));
  };

  // Details Tab Content
  const DetailsContent = () => (
    <TabsContent value="details" className="space-y-6">
      <Card>
        <div className="p-5 space-y-6">
          <h2 className="text-lg font-semibold text-ink">Meeting Details</h2>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="title">Title</Label>
              <Input
                id="title"
                name="title"
                value={formData.title}
                onChange={handleChange}
                placeholder="Enter meeting title"
                required
              />
            </div>
            <div>
              <Label htmlFor="meeting_type">Meeting Type</Label>
              <Select
                value={formData.meeting_type}
                onChange={e => setFormData({...formData, meeting_type: e.target.value})}
                options={[
                  { value: "team", label: "Team" },
                  { value: "board", label: "Board" },
                  { value: "client", label: "Client" },
                  { value: "one_on_one", label: "1:1" },
                  { value: "all_hands", label: "All Hands" },
                ]}
              />
            </div>
            <div>
              <Label htmlFor="scale">Scale</Label>
              <Select
                value={formData.scale}
                onChange={e => setFormData({...formData, scale: e.target.value})}
                options={[
                  { value: "small", label: "Small" },
                  { value: "medium", label: "Medium" },
                  { value: "large", label: "Large" },
                  { value: "enterprise", label: "Enterprise" },
                ]}
              />
            </div>
            <div>
              <Label htmlFor="status">Status</Label>
              <Select
                value={formData.status || "scheduled"}
                onChange={e => setFormData({...formData, status: e.target.value})}
                options={[
                  { value: "scheduled", label: "Scheduled" },
                  { value: "in_progress", label: "In Progress" },
                  { value: "completed", label: "Completed" },
                  { value: "cancelled", label: "Cancelled" },
                ]}
              />
            </div>
          </div>

          <div>
            <Label htmlFor="description">Description</Label>
            <Textarea
              id="description"
              name="description"
              value={formData.description}
              onChange={handleChange}
              rows={4}
              placeholder="Describe the purpose and goals of this meeting..."
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <Label htmlFor="scheduled_start">Start Time</Label>
              <input
                type="datetime-local"
                name="scheduled_start"
                value={formData.scheduled_start}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              />
            </div>
            <div>
              <Label htmlFor="scheduled_end">End Time</Label>
              <input
                type="datetime-local"
                name="scheduled_end"
                value={formData.scheduled_end}
                onChange={handleChange}
                className="w-full px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
              />
            </div>
          </div>

          <div>
            <Label htmlFor="project_id">Project (Optional)</Label>
            <Input
              name="project_id"
              value={formData.project_id}
              onChange={handleChange}
              placeholder="Select or enter project ID"
            />
          </div>
        </div>
      </Card>
    </TabsContent>
  );

  // Participants Tab Content
  const ParticipantsContent = () => (
    <TabsContent value="participants" className="space-y-6">
      <Card>
        <div className="p-5 space-y-6">
          <h2 className="text-lg font-semibold text-ink">Internal Participants</h2>
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input
                placeholder="Search users by name or email..."
                className="flex-1"
              />
              <Button variant="secondary">
                <UserPlus className="h-4 w-4 mr-1" />
                Add Participant
              </Button>
            </div>
            <div className="space-y-2">
              {formData.participant_ids.length === 0 ? (
                <p className="text-muted text-sm text-center py-4">No participants added yet</p>
              ) : (
                formData.participant_ids.map((id, index) => (
                  <div key={index} className="flex items-center justify-between p-3 bg-muted/50 rounded-lg">
                    <div className="flex items-center gap-3">
                      <Avatar name={`User ${id}`} className="h-8 w-8" />
                      <div>
                        <p className="font-medium text-sm">User {id}</p>
                        <p className="text-xs text-muted">Participant</p>
                      </div>
                    </div>
                    <Button variant="ghost" size="sm" onClick={() => removeParticipant(index)}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <div className="p-5 space-y-6">
          <h2 className="text-lg font-semibold text-ink">External Guests</h2>
          <div className="space-y-3">
            <div className="flex gap-2">
              <Input
                placeholder="Guest email address..."
                className="flex-1"
              />
              <Button variant="secondary">
                <UserPlus className="h-4 w-4 mr-1" />
                Add Guest
              </Button>
            </div>
            <p className="text-sm text-muted">External guests will receive an email invitation with a join link</p>
          </div>
        </div>
      </Card>
    </TabsContent>
  );

  // Settings Tab Content
  const SettingsContent = () => (
    <TabsContent value="settings" className="space-y-6">
      <Card>
        <div className="p-5 space-y-6">
          <h2 className="text-lg font-semibold text-ink">Meeting Features</h2>
          <div className="space-y-3">
            <label className="flex items-center gap-2 p-3 border border-line rounded-lg hover:bg-muted/50 cursor-pointer">
              <input type="checkbox" name="wait_room_enabled" checked={formData.wait_room_enabled} onChange={handleChange} className="w-4 h-4 rounded border-line text-brand focus:ring-brand" />
              <span className="font-medium">Waiting Room</span>
              <p className="text-xs text-muted ml-2">Require host approval to join</p>
            </label>
            <label className="flex items-center gap-2 p-3 border border-line rounded-lg hover:bg-muted/50 cursor-pointer">
              <input type="checkbox" name="chat_enabled" checked={formData.chat_enabled} onChange={handleChange} className="w-4 h-4 rounded border-line text-brand focus:ring-brand" />
              <span className="font-medium">Chat</span>
              <p className="text-xs text-muted ml-2">Enable meeting chat</p>
            </label>
            <label className="flex items-center gap-2 p-3 border border-line rounded-lg hover:bg-muted/50 cursor-pointer">
              <input type="checkbox" name="reactions_enabled" checked={formData.reactions_enabled} onChange={handleChange} className="w-4 h-4 rounded border-line text-brand focus:ring-brand" />
              <span className="font-medium">Reactions</span>
              <p className="text-xs text-muted ml-2">Enable emoji reactions</p>
            </label>
            <label className="flex items-center gap-2 p-3 border border-line rounded-lg hover:bg-muted/50 cursor-pointer">
              <input type="checkbox" name="screen_share_enabled" checked={formData.screen_share_enabled} onChange={handleChange} className="w-4 h-4 rounded border-line text-brand focus:ring-brand" />
              <span className="font-medium">Screen Sharing</span>
              <p className="text-xs text-muted ml-2">Allow screen sharing</p>
            </label>
          </div>
        </div>
      </Card>

      <Card>
        <div className="p-5 space-y-6">
          <h2 className="text-lg font-semibold text-ink">Access Control</h2>
          <div className="space-y-4">
            <label className="flex items-center gap-2 p-3 border border-line rounded-lg hover:bg-muted/50 cursor-pointer">
              <input type="checkbox" name="require_approval" checked={formData.require_approval} onChange={handleChange} className="w-4 h-4 rounded border-line text-brand focus:ring-brand" />
              <span className="font-medium">Require Approval</span>
              <p className="text-xs text-muted ml-2">Participants need host approval to join</p>
            </label>
            <label className="flex items-center gap-2 p-3 border border-line rounded-lg hover:bg-muted/50 cursor-pointer">
              <input type="checkbox" name="allow_external_guests" checked={formData.allow_external_guests} onChange={handleChange} className="w-4 h-4 rounded border-line text-brand focus:ring-brand" />
              <span className="font-medium">Allow External Guests</span>
              <p className="text-xs text-muted ml-2">Allow guests without VCOS accounts</p>
            </label>
            <label className="flex items-center gap-2 p-3 border border-line rounded-lg hover:bg-muted/50 cursor-pointer">
              <input type="checkbox" name="password_protected" checked={formData.password_protected} onChange={handleChange} className="w-4 h-4 rounded border-line text-brand focus:ring-brand" />
              <span className="font-medium">Password Protected</span>
              <p className="text-xs text-muted ml-2">Require password to join</p>
            </label>
            {formData.password_protected && (
              <div className="ml-6">
                <Input
                  type="password"
                  name="password"
                  value={formData.password}
                  onChange={handleChange}
                  placeholder="Meeting password"
                />
              </div>
            )}
          </div>
        </div>
      </Card>
    </TabsContent>
  );

  // Advanced Tab Content
  const AdvancedContent = () => (
    <TabsContent value="advanced" className="space-y-6">
      <Card>
        <div className="p-5 space-y-6">
          <h2 className="text-lg font-semibold text-ink">Advanced Settings</h2>
          <div className="space-y-4">
            <div>
              <Label className="block text-sm font-medium text-ink mb-1">Custom Settings (JSON)</Label>
              <textarea
                name="settings"
                value={JSON.stringify(formData.settings, null, 2)}
                onChange={(e) => {
                  try {
                    setFormData(prev => ({ ...prev, settings: JSON.parse(e.target.value) }));
                  } catch {
                    // Ignore invalid JSON
                  }
                }}
                rows={6}
                className="w-full px-4 py-2 border border-line rounded-lg bg-canvas font-mono text-sm focus:outline-none focus:ring-2 focus:ring-brand"
                placeholder='{"customField": "value"}'
              />
            </div>
            <div>
              <Label className="block text-sm font-medium text-ink mb-1">Materials (JSON)</Label>
              <textarea
                name="materials"
                value={JSON.stringify(formData.materials, null, 2)}
                onChange={(e) => {
                  try {
                    setFormData(prev => ({ ...prev, materials: JSON.parse(e.target.value) }));
                  } catch {
                    // Ignore invalid JSON
                  }
                }}
                rows={4}
                className="w-full px-4 py-2 border border-line rounded-lg bg-canvas font-mono text-sm focus:outline-none focus:ring-2 focus:ring-brand"
                placeholder='[{"type": "document", "id": "doc-123"}]'
              />
            </div>
          </div>
        </div>
      </Card>
    </TabsContent>
  );

  return (
    <div className="max-w-4xl mx-auto space-y-6 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-ink">Create New Meeting</h1>
          <p className="text-muted text-sm mt-1">Set up your meeting details and invite participants</p>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm" role="alert">
          {error}
        </div>
      )}

      <Tabs defaultValue="details" className="space-y-6">
        <TabsList className="grid w-full grid-cols-4 p-1 bg-canvas/50 border-b border-line">
          <TabsTrigger value="details" className="py-2 flex items-center gap-2">
            <FileText className="h-4 w-4" />
            Details
          </TabsTrigger>
          <TabsTrigger value="participants" className="py-2 flex items-center gap-2">
            <Users className="h-4 w-4" />
            Participants
          </TabsTrigger>
          <TabsTrigger value="settings" className="py-2 flex items-center gap-2">
            <Settings className="h-4 w-4" />
            Settings
          </TabsTrigger>
          <TabsTrigger value="advanced" className="py-2 flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Advanced
          </TabsTrigger>
        </TabsList>

        <DetailsContent />
        <ParticipantsContent />
        <SettingsContent />
        <AdvancedContent />
      </Tabs>

      {/* Footer Actions */}
      <div className="flex items-center justify-end gap-3 pt-4 border-t border-line">
        <Button variant="secondary" onClick={() => router.back()}>
          Cancel
        </Button>
        <Button onClick={handleSubmit} disabled={loading || !formData.title.trim()}>
          {loading ? (
            <span className="flex items-center gap-2">
              <div className="animate-spin rounded-full h-4 w-4 border-2 border-white border-t-transparent" />
              Creating...
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <Plus className="h-4 w-4" />
              Create Meeting
            </span>
          )}
        </Button>
      </div>
    </div>
  );
}