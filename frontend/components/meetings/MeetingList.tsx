"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Calendar,
  Clock,
  Users,
  Video,
  Mic,
  Settings,
  Plus,
  Search,
  Filter,
  ChevronDown,
  ChevronUp,
  MoreHorizontal,
  Trash2,
  Edit,
  Play,
  Pause,
  Stop,
  Record,
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
  Camera,
  CameraOff,
  Wifi,
  WifiOff,
  Battery,
  BatteryLow,
  Settings as SettingsIcon,
  Cpu,
  HardDrive,
  Monitor,
  Smartphone,
  Tablet,
  Laptop,
  Server,
  Database,
  Cloud,
  Globe,
  Network,
  Shield as ShieldIcon,
  Lock as LockIcon,
  Key,
  Unlock,
  Heart,
  Star,
  Flag,
  Bookmark,
  Tag,
  Link,
  Hash,
  ArrowRight,
  ChevronLeft,
  ChevronRight,
  Loader2,
  Bell,
  Clock as ClockIcon,
  BarChart2 as BarChart2Icon,
  Shield as ShieldIcon2,
  Briefcase,
  Menu,
  X,
  RefreshCw,
  Activity,
  UserPlus,
  Mail,
  Phone,
  MapPin,
  Building2,
  FileText,
  Image,
  Presentation,
  ScreenShare,
  Whiteboard,
  PenTool,
  Highlighter,
  Eraser,
  Laser,
  Pointer,
  Hand,
  Smile,
  Heart,
  ThumbsUp,
  ThumbsDown,
  Clap,
  PartyPopper,
  Zap,
  Sparkles,
  Brain,
  Target,
  TrendingUp,
  TrendingDown,
  ArrowUp,
  ArrowDown,
  Minus,
  Plus as PlusIcon,
  Divide,
  Multiply,
  Equal,
  NotEqual,
  GreaterThan,
  LessThan,
  GreaterThanOrEqual,
  LessThanOrEqual,
  Percent,
  DollarSign,
  Euro,
  Pound,
  Yen,
  Ruble,
  Bitcoin,
  Ethereum,
  Litecoin,
  Ripple,
  Dogecoin,
  Cardano,
  Polkadot,
  Solana,
  Chainlink,
  Uniswap,
  Aave,
  Compound,
  Maker,
  Synthetix,
  Yearn,
  Curve,
  Balancer,
  SushiSwap,
  PancakeSwap,
  QuickSwap,
  TraderJoe,
  Pangolin,
  Benqi,
  YieldYak,
  Autofarm,
  Beefy,
  Harvest,
  Pickle,
  Ren,
  Alchemix,
  Rari,
  Index,
  TokenSets,
  SetProtocol,
  Enzyme,
  dHedge,
  BasketDAO,
  PieDAO,
  IndexCoop,
  TokenSets,
  SetProtocol,
  Enzyme,
  dHedge,
  BasketDAO,
  PieDAO,
  IndexCoop,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { Avatar } from "@/components/ui/Avatar";
import { Dropdown, MenuItem } from "@/components/ui/Dropdown";
import { Modal } from "@/components/ui/Modal";
import { Card } from "@/components/ui/Card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/Tabs";
import {
  Table,
  TableHeader,
  TableRow,
  TableCell,
  TableHeaderCell,
} from "@/components/ui/Table";
import { Spinner } from "@/components/ui/Spinner";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorState } from "@/components/ui/ErrorState";
import { Progress } from "@/components/ui/Progress";
import { Toaster, toastError, toastSuccess } from "@/components/ui/Toaster";
import { classNames } from "@/lib/utils";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import type {
  Meeting,
  MeetingType,
  MeetingStatus,
  MeetingScale,
} from "@/types";

const MEETING_TYPE_LABELS: Record<string, string> = {
  standard: "Standard",
  standup: "Standup",
  planning: "Planning",
  review: "Review",
  one_on_one: "1:1",
  town_hall: "Town Hall",
  webinar: "Webinar",
  conference: "Conference",
  board: "Board Meeting",
  interview: "Interview",
  sales: "Sales Call",
  support: "Support",
  training: "Training",
  workshop: "Workshop",
};

const MEETING_STATUS_LABELS: Record<string, string> = {
  draft: "Draft",
  scheduled: "Scheduled",
  waiting: "Waiting",
  active: "Active",
  paused: "Paused",
  ended: "Ended",
  cancelled: "Cancelled",
};

const MEETING_STATUS_TONES: Record<
  string,
  "success" | "warning" | "danger" | "brand" | "neutral"
> = {
  draft: "neutral",
  scheduled: "brand",
  waiting: "warning",
  active: "success",
  paused: "warning",
  ended: "neutral",
  cancelled: "danger",
};

const SCALE_LABELS: Record<string, string> = {
  small: "Small (2-10)",
  team: "Team (10-50)",
  department: "Department (50-200)",
  town_hall: "Town Hall (200-1K)",
  webinar: "Webinar (1K-10K)",
  conference: "Conference (10K+)",
};

interface MeetingListProps {
  className?: string;
  onMeetingClick?: (meeting: Meeting) => void;
}

export function MeetingList({ className, onMeetingClick }: MeetingListProps) {
  const { organization, ready } = useAuth();
  const router = useRouter();
  const [meetings, setMeetings] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filterStatus, setFilterStatus] = useState<string>("all");
  const [searchQuery, setSearchQuery] = useState("");

  const fetchMeetings = useCallback(async () => {
    if (!ready || !organization?.id) return;
    try {
      setLoading(true);
      const data = await api<Meeting[]>("/meetings");
      setMeetings(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load meetings");
    } finally {
      setLoading(false);
    }
  }, [ready, organization?.id]);

  useEffect(() => {
    fetchMeetings();
  }, [fetchMeetings]);

  const filteredMeetings = useMemo(() => {
    return meetings.filter((meeting) => {
      const matchesStatus =
        filterStatus === "all" || meeting.status === filterStatus;
      const matchesSearch =
        meeting.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        meeting.description?.toLowerCase().includes(searchQuery.toLowerCase());
      return matchesStatus && matchesSearch;
    });
  }, [meetings, filterStatus, searchQuery]);

  const handleCreateMeeting = async () => {
    router.push("/meetings/new");
  };

  const handleStartMeeting = async (meeting: Meeting) => {
    try {
      await api<Meeting>(`/meetings/${meeting.id}/start`, { method: "POST" });
      toastSuccess("Meeting started");
      fetchMeetings();
    } catch (err) {
      toastError(
        err instanceof Error ? err.message : "Failed to start meeting",
      );
    }
  };

  const handleJoinMeeting = async (meeting: Meeting) => {
    try {
      const result = await api<{
        media_token: string;
        media_url: string;
        room_name: string;
      }>(`/meetings/${meeting.id}/join`, { method: "POST" });
      // Navigate to meeting room
      router.push(`/meetings/${meeting.id}/room?token=${result.media_token}`);
    } catch (err) {
      toastError(err instanceof Error ? err.message : "Failed to join meeting");
    }
  };

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner label="Loading..." />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 bg-line rounded w-1/4" />
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-24 bg-line rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <ErrorState
        title="Could not load meetings"
        message={error}
        onRetry={fetchMeetings}
      />
    );
  }

  if (filteredMeetings.length === 0) {
    return (
      <EmptyState
        icon={Video}
        title="No meetings found"
        description="Create your first meeting to get started"
        action={{
          label: "Create Meeting",
          onClick: handleCreateMeeting,
        }}
      />
    );
  }

  return (
    <div className={cn("space-y-6", className)}>
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-ink">Meetings</h1>
          <p className="text-muted text-sm mt-1">
            Manage your meetings, conferences, and presentations
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchMeetings}>
            <RefreshCw className="h-4 w-4 mr-1" />
            Refresh
          </Button>
          <Button onClick={handleCreateMeeting}>
            <Plus className="h-4 w-4 mr-1" />
            New Meeting
          </Button>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1">
          <Input
            placeholder="Search meetings..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="max-w-md"
          />
        </div>
        <div className="flex items-center gap-2">
          <select
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
            className="px-4 py-2 border border-line rounded-lg bg-canvas focus:outline-none focus:ring-2 focus:ring-brand"
          >
            <option value="all">All Status</option>
            <option value="draft">Draft</option>
            <option value="scheduled">Scheduled</option>
            <option value="waiting">Waiting</option>
            <option value="active">Active</option>
            <option value="paused">Paused</option>
            <option value="ended">Ended</option>
            <option value="cancelled">Cancelled</option>
          </select>
        </div>
      </div>

      {/* Meetings Grid */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {filteredMeetings.map((meeting) => (
          <MeetingCard
            key={meeting.id}
            meeting={meeting}
            onClick={() =>
              onMeetingClick?.(meeting) ||
              router.push(`/meetings/${meeting.id}`)
            }
            onStart={handleStartMeeting}
            onJoin={handleJoinMeeting}
          />
        ))}
      </div>

      {filteredMeetings.length === meetings.length && meetings.length > 0 && (
        <div className="text-center py-8 text-muted">
          <p>Showing all {meetings.length} meetings</p>
        </div>
      )}
    </div>
  );
}

interface MeetingCardProps {
  meeting: Meeting;
  onClick: () => void;
  onStart: (meeting: Meeting) => void;
  onJoin: (meeting: Meeting) => void;
}

function MeetingCard({ meeting, onClick, onStart, onJoin }: MeetingCardProps) {
  const statusTone = MEETING_STATUS_TONES[meeting.status] || "neutral";
  const isActive = meeting.status === "active";
  const isUpcoming =
    meeting.status === "scheduled" &&
    meeting.scheduled_start &&
    new Date(meeting.scheduled_start) > new Date();
  const isPast =
    meeting.status === "ended" ||
    (meeting.scheduled_end && new Date(meeting.scheduled_end) < new Date());

  return (
    <Card
      className="flex flex-col h-full transition-all hover:shadow-lg hover:border-brand/30"
      onClick={onClick}
    >
      <div className="flex items-start justify-between p-4 border-b border-line">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <h3 className="font-medium text-ink truncate">{meeting.title}</h3>
            <Badge tone={statusTone}>
              {MEETING_STATUS_LABELS[meeting.status] || meeting.status}
            </Badge>
            <Badge variant="outline" className="text-xs">
              {SCALE_LABELS[meeting.scale] || meeting.scale}
            </Badge>
          </div>
          <p className="text-sm text-muted truncate mb-2">
            {meeting.description || "No description"}
          </p>
        </div>
        {isActive && (
          <Badge tone="success" className="ml-2 animate-pulse">
            <span className="flex items-center gap-1">
              <span className="h-2 w-2 rounded-full bg-success animate-pulse" />
              Live
            </span>
          </Badge>
        )}
      </div>

      <div className="p-4 space-y-3 flex-1">
        {/* Meeting Type */}
        <div className="flex items-center gap-2 text-sm text-muted">
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-brand/10 text-brand">
            <Video className="h-3.5 w-3.5" />
            {MEETING_TYPE_LABELS[meeting.meeting_type] || meeting.meeting_type}
          </span>
          <span className="flex items-center gap-1 px-2 py-1 rounded bg-muted/50">
            <Users className="h-3.5 w-3.5" />
            {meeting.scale}
          </span>
        </div>

        {/* Schedule */}
        {meeting.scheduled_start && (
          <div className="flex items-center gap-2 text-sm text-muted">
            <Calendar className="h-3.5 w-3.5" />
            <span>
              {new Date(meeting.scheduled_start).toLocaleDateString()} at
              {new Date(meeting.scheduled_start).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
            {meeting.scheduled_end && (
              <>
                <span>–</span>
                <span>
                  {new Date(meeting.scheduled_end).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </>
            )}
          </div>
        )}

        {/* Project */}
        {meeting.project_id && (
          <div className="flex items-center gap-2 text-sm text-muted">
            <Briefcase className="h-3.5 w-3.5" />
            <span>Project: {meeting.project_id}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2 pt-2 border-t border-line">
          {meeting.status === "scheduled" && (
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={(e) => {
                e.stopPropagation();
                onJoin({ id: meeting.id } as any);
              }}
            >
              <Calendar className="h-3.5 w-3.5 mr-1" />
              Join
            </Button>
          )}
          {meeting.status === "waiting" && (
            <Button
              variant="secondary"
              size="sm"
              className="flex-1"
              onClick={(e) => {
                e.stopPropagation();
                onJoin({ id: meeting.id } as any);
              }}
            >
              <Play className="h-3.5 w-3.5 mr-1" />
              Start
            </Button>
          )}
          {meeting.status === "active" && (
            <Button
              variant="primary"
              size="sm"
              className="flex-1"
              onClick={(e) => {
                e.stopPropagation();
                onJoin({ id: meeting.id } as any);
              }}
            >
              <Video className="h-3.5 w-3.5 mr-1" />
              Join Now
            </Button>
          )}
          {meeting.status === "active" && (
            <Button
              variant="danger"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
              }}
            >
              <Stop className="h-3.5 w-3.5 mr-1" />
              End
            </Button>
          )}
          {meeting.status !== "active" && meeting.status !== "ended" && (
            <Button
              variant="outline"
              size="sm"
              onClick={(e) => {
                e.stopPropagation();
                onStart({ id: meeting.id } as any);
              }}
            >
              <Play className="h-3.5 w-3.5 mr-1" />
              Start
            </Button>
          )}
        </div>
      </div>

      <div className="p-4 border-t border-line bg-muted/30">
        <div className="flex items-center justify-between text-xs text-muted">
          <span>
            Created {new Date(meeting.created_at).toLocaleDateString()}
          </span>
          <span>{meeting.meeting_type}</span>
        </div>
      </div>
    </Card>
  );
}

export { MeetingList, MeetingCard };
