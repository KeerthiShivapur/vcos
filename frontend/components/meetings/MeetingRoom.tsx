"use client";

import { useState, useEffect, useCallback, useRef, useMemo } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Mic,
  MicOff,
  Camera,
  CameraOff,
  Users,
  MessageSquare,
  Share,
  MoreHorizontal,
  Settings,
  LogOut,
  Circle,
  Square,
  Play,
  Pause,
  Volume2,
  VolumeX,
  Fullscreen,
  Minimize,
  ChevronDown,
  ChevronUp,
  LayoutGrid,
  Grid,
  Monitor,
  Smartphone,
  Tablet,
  Laptop,
  Server,
  Database,
  Cloud,
  Globe,
  Network,
  Shield,
  Lock,
  Key,
  Unlock,
  Heart,
  Star,
  Flag,
  Bookmark,
  Tag,
  Link,
  Hash,
  Key as KeyIcon,
  Lock as LockIcon,
  Unlock as UnlockIcon,
  Shield as ShieldIcon,
  Eye,
  EyeOff,
  Volume2 as Volume2Icon,
  VolumeX as VolumeXIcon,
  Mic as MicIcon,
  MicOff as MicOffIcon,
  Camera as CameraIcon,
  CameraOff as CameraOffIcon,
  Wifi,
  WifiOff,
  Battery,
  BatteryLow,
  Settings as SettingsIcon,
  Cpu,
  HardDrive,
  Monitor as MonitorIcon,
  Smartphone as SmartphoneIcon,
  Tablet as TabletIcon,
  Laptop as LaptopIcon,
  Server as ServerIcon,
  Database as DatabaseIcon,
  Cloud as CloudIcon,
  Globe as GlobeIcon,
  Network as NetworkIcon,
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
import { Spinner } from "@/components/ui/Spinner";
import { Toaster, toastError, toastSuccess } from "@/components/ui/Toaster";
import { classNames } from "@/lib/utils";
import { api } from "@/lib/api";
import { useAuth } from "@/hooks/useAuth";
import type { Meeting, MeetingParticipant } from "@/types";

interface MeetingRoomProps {
  meetingId: string;
  className?: string;
}

export function MeetingRoom({ meetingId, className }: MeetingRoomProps) {
  const { user, ready } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const token = searchParams.get("token");

  const [meeting, setMeeting] = useState<any>(null);
  const [participants, setParticipants] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localVideoEnabled, setLocalVideoEnabled] = useState(true);
  const [localAudioEnabled, setLocalAudioEnabled] = useState(true);
  const [screenSharing, setScreenSharing] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [participantsOpen, setParticipantsOpen] = useState(true);
  const [chatMessages, setChatMessages] = useState<any[]>([]);
  const [newMessage, setNewMessage] = useState("");
  const [layout, setLayout] = useState<"grid" | "speaker" | "pip">("grid");
  const [fullscreen, setFullscreen] = useState(false);
  const [recording, setRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [connectionQuality, setConnectionQuality] = useState<
    "excellent" | "good" | "fair" | "poor"
  >("excellent");

  // LiveKit refs
  const roomRef = useRef<any>(null);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const remoteVideosRef = useRef<Map<string, HTMLVideoElement>>(new Map());

  const fetchMeeting = useCallback(async () => {
    try {
      const data = await api(`/meetings/${meetingId}`);
      setMeeting(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load meeting");
    }
  }, [meetingId]);

  const fetchParticipants = useCallback(async () => {
    try {
      const data = await api<any[]>(`/meetings/${meetingId}/participants`);
      setParticipants(data);
    } catch (err) {
      console.error("Failed to load participants:", err);
    }
  }, [meetingId]);

  useEffect(() => {
    if (!ready) return;
    fetchMeeting();
    fetchParticipants();
  }, [ready, fetchMeeting, fetchParticipants]);

  useEffect(() => {
    if (token) {
      // Initialize LiveKit room with token
      initializeLiveKit(token);
    }
  }, [token]);

  const initializeLiveKit = async (token: string) => {
    try {
      // Dynamic import for LiveKit
      const LiveKit = await import("livekit-client");

      const room = new LiveKit.Room({
        adaptiveStream: true,
        dynacast: true,
      });

      // Event handlers
      room.on("trackSubscribed", (track, publication, participant) => {
        if (track.kind === LiveKit.Track.Kind.Video) {
          const videoElement = document.createElement("video");
          videoElement.srcObject = new MediaStream([track.mediaStreamTrack]);
          videoElement.autoplay = true;
          videoElement.playsInline = true;
          videoElement.id = `video-${participant.identity}`;
          remoteVideosRef.current.set(participant.identity, videoElement);
        }
      });

      room.on("trackUnsubscribed", (track, publication, participant) => {
        const videoElement = remoteVideosRef.current.get(participant.identity);
        if (videoElement) {
          videoElement.srcObject = null;
          remoteVideosRef.current.delete(participant.identity);
        }
      });

      room.on("participantConnected", (participant) => {
        fetchParticipants();
      });

      room.on("participantDisconnected", (participant) => {
        fetchParticipants();
      });

      room.on("disconnected", () => {
        toastError("Disconnected from meeting");
      });

      // Connect to room
      const wsUrl =
        process.env.NEXT_PUBLIC_LIVEKIT_URL || "wss://livekit.vcos.io";
      await room.connect(wsUrl, token);

      roomRef.current = room;

      // Publish local tracks
      await room.localParticipant.setCameraEnabled(localVideoEnabled);
      await room.localParticipant.setMicrophoneEnabled(localAudioEnabled);

      // Update connection quality
      const updateQuality = () => {
        if (roomRef.current) {
          const quality = roomRef.current.getConnectionQuality();
          setConnectionQuality(quality as any);
        }
      };
      const qualityInterval = setInterval(updateQuality, 5000);

      // Cleanup
      return () => {
        clearInterval(qualityInterval);
        room.disconnect();
      };
    } catch (err) {
      console.error("Failed to initialize LiveKit:", err);
      setError("Failed to connect to meeting room");
    }
  };

  const toggleVideo = async () => {
    if (roomRef.current) {
      const enabled = !localVideoEnabled;
      await roomRef.current.localParticipant.setCameraEnabled(enabled);
      setLocalVideoEnabled(enabled);
    }
  };

  const toggleAudio = async () => {
    if (roomRef.current) {
      const enabled = !localAudioEnabled;
      await roomRef.current.localParticipant.setMicrophoneEnabled(enabled);
      setLocalAudioEnabled(enabled);
    }
  };

  const toggleScreenShare = async () => {
    if (roomRef.current) {
      if (!screenSharing) {
        try {
          await roomRef.current.localParticipant.setScreenShareEnabled(true);
          setScreenSharing(true);
        } catch (err) {
          toastError("Failed to start screen sharing");
        }
      } else {
        await roomRef.current.localParticipant.setScreenShareEnabled(false);
        setScreenSharing(false);
      }
    }
  };

  const leaveMeeting = async () => {
    if (roomRef.current) {
      await roomRef.current.disconnect();
    }
    await api(`/meetings/${meetingId}/leave`, { method: "POST" });
    router.push("/meetings");
  };

  const toggleRecording = async () => {
    if (!recording) {
      try {
        await api(`/meetings/${meetingId}/recording/start`, { method: "POST" });
        setRecording(true);
        startRecordingTimer();
        toastSuccess("Recording started");
      } catch (err) {
        toastError("Failed to start recording");
      }
    } else {
      try {
        await api(`/meetings/${meetingId}/recording/stop`, { method: "POST" });
        setRecording(false);
        stopRecordingTimer();
        toastSuccess("Recording stopped");
      } catch (err) {
        toastError("Failed to stop recording");
      }
    }
  };

  const startRecordingTimer = () => {
    const interval = setInterval(() => {
      setRecordingTime((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  };

  const stopRecordingTimer = () => {
    // Timer cleanup handled by useEffect
  };

  const sendMessage = async () => {
    if (!newMessage.trim()) return;
    try {
      await api(`/meetings/${meetingId}/chat`, {
        method: "POST",
        body: { message: newMessage },
      });
      setNewMessage("");
    } catch (err) {
      toastError("Failed to send message");
    }
  };

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-brand border-t-transparent mx-auto mb-4" />
          <p className="text-muted">Loading meeting...</p>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Spinner label="Joining meeting..." />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <ErrorState
          title="Could not join meeting"
          message={error}
          onRetry={fetchMeeting}
        />
      </div>
    );
  }

  if (!meeting) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background">
        <Spinner label="Loading meeting..." />
      </div>
    );
  }

  // Local video element
  const localVideoStream =
    roomRef.current?.localParticipant?.videoTrack?.mediaStreamTrack;

  return (
    <div
      className={cn(
        "flex h-screen w-full bg-background overflow-hidden",
        className,
      )}
    >
      {/* Meeting Header */}
      <div className="flex items-center justify-between h-14 px-4 border-b border-line bg-canvas/80 backdrop-blur-sm z-10">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="icon"
            onClick={leaveMeeting}
            className="text-muted hover:text-red-500"
          >
            <LogOut className="h-5 w-5" />
          </Button>
          <div>
            <h1 className="font-semibold text-ink">
              {meeting?.title || "Meeting"}
            </h1>
            <div className="flex items-center gap-2 text-xs text-muted">
              <Badge
                tone={meeting?.status === "active" ? "success" : "neutral"}
                className="gap-1"
              >
                {meeting?.status === "active" && (
                  <span className="flex items-center gap-1">
                    <span className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
                    Live
                  </span>
                )}
                {meeting?.status || "Unknown"}
              </Badge>
              {meeting?.scale && (
                <Badge variant="outline" className="text-xs">
                  {meeting.scale}
                </Badge>
              )}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Connection Quality */}
          <div className="flex items-center gap-1">
            <span
              className={`h-2 w-2 rounded-full ${
                connectionQuality === "excellent"
                  ? "bg-success"
                  : connectionQuality === "good"
                    ? "bg-brand"
                    : connectionQuality === "fair"
                      ? "bg-warning"
                      : "bg-danger"
              }`}
            />
            <span className="text-xs text-muted capitalize">
              {connectionQuality}
            </span>
          </div>

          {/* Recording Timer */}
          {recording && (
            <Button
              variant="danger"
              size="sm"
              onClick={toggleRecording}
              className="animate-pulse"
            >
              <Circle className="h-4 w-4 mr-1" />
              {Math.floor(recordingTime / 60)}:
              {String(recordingTime % 60).padStart(2, "0")}
            </Button>
          )}

          {/* Fullscreen */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setFullscreen(!fullscreen)}
          >
            {fullscreen ? (
              <Minimize className="h-4 w-4" />
            ) : (
              <Fullscreen className="h-4 w-4" />
            )}
          </Button>

          {/* Settings */}
          <Dropdown>
            <Button variant="ghost" size="icon">
              <Settings className="h-4 w-4" />
            </Button>
            <MenuItem onClick={() => setLayout("grid")}>Grid View</MenuItem>
            <MenuItem onClick={() => setLayout("speaker")}>
              Speaker View
            </MenuItem>
            <MenuItem onClick={() => setLayout("pip")}>
              Picture-in-Picture
            </MenuItem>
            <hr className="my-1 border-line" />
            <MenuItem onClick={toggleRecording}>
              {recording ? "Stop Recording" : "Start Recording"}
            </MenuItem>
            <MenuItem onClick={leaveMeeting} className="text-red-500">
              Leave Meeting
            </MenuItem>
          </Dropdown>
        </div>
      </div>

      {/* Main Meeting Area */}
      <div className="flex-1 flex overflow-hidden">
        {/* Video Grid */}
        <div
          className={cn(
            "flex-1 flex",
            fullscreen ? "fixed inset-0 z-50 bg-background" : "",
          )}
        >
          <div
            className={cn(
              "flex-1 flex",
              layout === "grid" &&
                "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2",
              layout === "speaker" && "flex",
              layout === "pip" && "flex",
            )}
          >
            {/* Local Video */}
            <VideoTile
              participant={null}
              videoRef={localVideoRef}
              name={user?.full_name || user?.username || "You"}
              isLocal={true}
              audioEnabled={localAudioEnabled}
              videoEnabled={localVideoEnabled}
              screenSharing={screenSharing}
              isSpeaking={false}
            />

            {/* Remote Videos */}
            {Array.from(remoteVideosRef.current.entries()).map(
              ([participantId, videoEl]) => (
                <VideoTile
                  key={participantId}
                  participant={participants.find((p) => p.id === participantId)}
                  videoRef={videoEl}
                  name={
                    participants.find((p) => p.id === participantId)
                      ?.display_name || "Participant"
                  }
                  isLocal={false}
                />
              ),
            )}

            {/* Empty state */}
            {participants.length === 0 && !remoteVideosRef.current.size && (
              <div className="flex-1 flex items-center justify-center text-muted">
                <div className="text-center">
                  <Users className="h-12 w-12 mx-auto mb-3 opacity-50" />
                  <p>No other participants yet</p>
                  <p className="text-sm">
                    Share the meeting link to invite others
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Recording Indicator */}
          {recording && (
            <div className="absolute bottom-4 right-4 animate-pulse">
              <div className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-red-500/90 text-white text-sm font-medium">
                <Circle className="h-4 w-4" />
                <span>REC</span>
                <span className="font-mono">
                  {Math.floor(recordingTime / 60)}:
                  {String(recordingTime % 60).padStart(2, "0")}
                </span>
              </div>
            </div>
          )}

          {/* Picture-in-Picture for local video when screen sharing */}
          {screenSharing && layout === "pip" && (
            <div className="absolute bottom-4 right-4 w-64 h-36 rounded-lg border border-line overflow-hidden shadow-xl z-20">
              <video
                ref={localVideoRef}
                autoPlay
                playsInline
                muted
                className="w-full h-full object-cover"
              />
            </div>
          )}
        </div>

        {/* Side Panel */}
        <div
          className={cn(
            "w-80 flex flex-col border-l border-line bg-canvas/50",
            !participantsOpen && "hidden",
          )}
        >
          <Tabs defaultValue="participants" className="flex-1">
            <TabsList className="grid w-full grid-cols-2 p-1 bg-canvas/50 border-b border-line">
              <TabsTrigger value="participants">
                <Users className="h-4 w-4 mr-1" />
                Participants ({participants.length})
              </TabsTrigger>
              <TabsTrigger value="chat">
                <MessageSquare className="h-4 w-4 mr-1" />
                Chat
              </TabsTrigger>
            </TabsList>

            <TabsContent
              value="participants"
              className="flex-1 overflow-y-auto p-3"
            >
              <div className="space-y-2">
                {/* Local User */}
                <ParticipantTile
                  participant={{
                    id: user?.id,
                    display_name: user?.full_name || user?.username || "You",
                    avatar_url: user?.avatar_url,
                    role: "host",
                    status: "joined",
                    audio_enabled: localAudioEnabled,
                    video_enabled: localVideoEnabled,
                  }}
                  isLocal={true}
                  onToggleAudio={toggleAudio}
                  onToggleVideo={toggleVideo}
                />

                {/* Remote Participants */}
                {participants.map((p) => (
                  <ParticipantTile key={p.id} participant={p} isLocal={false} />
                ))}

                {participants.length === 0 && (
                  <div className="text-center py-8 text-muted">
                    <Users className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    <p>No other participants</p>
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="chat" className="flex-1 flex flex-col p-3">
              <div className="flex-1 overflow-y-auto space-y-3 mb-3">
                {chatMessages.map((msg, idx) => (
                  <ChatMessage
                    key={idx}
                    message={msg}
                    isOwn={msg.user_id === user?.id}
                  />
                ))}
                {chatMessages.length === 0 && (
                  <div className="text-center py-8 text-muted">
                    <MessageSquare className="h-8 w-8 mx-auto mb-2 opacity-50" />
                    <p>No messages yet</p>
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <Input
                  value={newMessage}
                  onChange={(e) => setNewMessage(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                  placeholder="Type a message..."
                  className="flex-1"
                />
                <Button onClick={sendMessage} disabled={!newMessage.trim()}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </TabsContent>
          </Tabs>
        </div>
      </div>

      {/* Bottom Toolbar */}
      <div className="flex items-center justify-center gap-3 h-16 px-4 border-t border-line bg-canvas/80 backdrop-blur-sm z-10">
        <div className="flex items-center gap-2">
          <Button
            variant={localAudioEnabled ? "default" : "secondary"}
            size="icon"
            onClick={toggleAudio}
            className={localAudioEnabled ? "bg-brand/10 text-brand" : ""}
          >
            {localAudioEnabled ? (
              <Mic className="h-5 w-5" />
            ) : (
              <MicOff className="h-5 w-5" />
            )}
          </Button>
          <Button
            variant={localVideoEnabled ? "default" : "secondary"}
            size="icon"
            onClick={toggleVideo}
            className={localVideoEnabled ? "bg-brand/10 text-brand" : ""}
          >
            {localVideoEnabled ? (
              <Camera className="h-5 w-5" />
            ) : (
              <CameraOff className="h-5 w-5" />
            )}
          </Button>
          <Button
            variant={screenSharing ? "default" : "secondary"}
            size="icon"
            onClick={toggleScreenShare}
            className={screenSharing ? "bg-brand/10 text-brand" : ""}
          >
            <Monitor className="h-5 w-5" />
          </Button>
        </div>

        <div className="flex-1" />

        <div className="flex items-center gap-2">
          <Button
            variant={chatOpen ? "default" : "secondary"}
            size="icon"
            onClick={() => setChatOpen(!chatOpen)}
            className={chatOpen ? "bg-brand/10 text-brand" : ""}
          >
            <MessageSquare className="h-5 w-5" />
          </Button>
          <Button
            variant={participantsOpen ? "default" : "secondary"}
            size="icon"
            onClick={() => setParticipantsOpen(!participantsOpen)}
            className={participantsOpen ? "bg-brand/10 text-brand" : ""}
          >
            <Users className="h-5 w-5" />
          </Button>
          <Button
            variant={recording ? "danger" : "secondary"}
            size="icon"
            onClick={toggleRecording}
            className={recording ? "animate-pulse" : ""}
          >
            <Circle className="h-5 w-5" />
          </Button>
          <Button variant="danger" size="icon" onClick={leaveMeeting}>
            <LogOut className="h-5 w-5" />
          </Button>
        </div>
      </div>
    </div>
  );
}

interface VideoTileProps {
  participant: any;
  videoRef: React.RefObject<HTMLVideoElement>;
  name: string;
  isLocal: boolean;
  audioEnabled?: boolean;
  videoEnabled?: boolean;
  screenSharing?: boolean;
  isSpeaking?: boolean;
}

function VideoTile({
  participant,
  videoRef,
  name,
  isLocal,
  audioEnabled,
  videoEnabled,
  screenSharing,
  isSpeaking,
}: VideoTileProps) {
  return (
    <div className="relative flex flex-col min-w-0 bg-muted/30 rounded-lg overflow-hidden border border-line/50">
      <div className="relative aspect-video bg-black flex items-center justify-center">
        {videoRef.current && videoRef.current.srcObject ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted={isLocal}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-muted/50">
            <div className="text-center text-muted">
              <User className="h-12 w-12 mx-auto mb-2" />
              <p className="text-sm">{name}</p>
              {!videoEnabled && (
                <p className="text-xs text-muted">Camera off</p>
              )}
            </div>
          </div>
        )}
        {isSpeaking && (
          <div className="absolute inset-0 border-2 border-brand/50 animate-pulse rounded-lg pointer-events-none" />
        )}
        {screenSharing && (
          <div className="absolute top-2 left-2 flex items-center gap-1 px-2 py-1 rounded bg-brand/90 text-white text-xs">
            <Monitor className="h-3 w-3" />
            Sharing
          </div>
        )}
      </div>
      <div className="px-3 py-2 flex items-center justify-between">
        <span className="font-medium text-sm truncate flex-1">{name}</span>
        <div className="flex items-center gap-1">
          {!isLocal && audioEnabled !== false && (
            <Mic className="h-3.5 w-3.5 text-success" />
          )}
          {!isLocal && videoEnabled !== false && (
            <Camera className="h-3.5 w-3.5 text-success" />
          )}
        </div>
      </div>
    </div>
  );
}

interface ParticipantTileProps {
  participant: any;
  isLocal: boolean;
  onToggleAudio?: () => void;
  onToggleVideo?: () => void;
}

function ParticipantTile({
  participant,
  isLocal,
  onToggleAudio,
  onToggleVideo,
}: ParticipantTileProps) {
  return (
    <div className="flex items-center gap-3 p-2 rounded-lg hover:bg-muted/50 transition-colors">
      <Avatar
        src={participant.avatar_url}
        alt={participant.display_name || participant.name || "User"}
        className="h-9 w-9"
        status={participant.audio_enabled ? "online" : "offline"}
      />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium text-sm truncate">
            {participant.display_name || participant.name || "User"}
            {isLocal && <span className="text-xs text-muted ml-1">(You)</span>}
          </span>
          <Badge variant="outline" className="text-xs capitalize">
            {participant.role || "participant"}
          </Badge>
        </div>
        <div className="flex items-center gap-2 text-xs text-muted">
          {participant.audio_enabled ? (
            <Mic className="h-3 w-3 text-success" />
          ) : (
            <MicOff className="h-3 w-3 text-danger" />
          )}
          {participant.video_enabled ? (
            <Camera className="h-3 w-3 text-success" />
          ) : (
            <CameraOff className="h-3 w-3 text-danger" />
          )}
        </div>
      </div>
      {!isLocal && (
        <Dropdown>
          <Button variant="ghost" size="icon" className="h-8 w-8">
            <MoreHorizontal className="h-4 w-4" />
          </Button>
          <MenuItem>Make Co-Host</MenuItem>
          <MenuItem>Mute</MenuItem>
          <MenuItem className="text-red-500">Remove</MenuItem>
        </Dropdown>
      )}
    </div>
  );
}

interface ChatMessageProps {
  message: any;
  isOwn: boolean;
}

function ChatMessage({ message, isOwn }: ChatMessageProps) {
  return (
    <div className={cn("flex gap-2", isOwn && "flex-row-reverse")}>
      {!isOwn && (
        <Avatar
          src={message.avatar_url}
          alt={message.name}
          className="h-7 w-7 shrink-0"
        />
      )}
      <div className={cn("max-w-[70%] flex flex-col", isOwn && "items-end")}>
        {!isOwn && (
          <span className="text-xs text-muted mb-1">{message.name}</span>
        )}
        <div
          className={cn(
            "px-3 py-2 rounded-2xl text-sm",
            isOwn
              ? "bg-brand text-white rounded-br-none"
              : "bg-muted text-ink rounded-bl-none",
          )}
        >
          {message.content}
        </div>
        <span className="text-[10px] text-muted mt-1 px-1">
          {new Date(message.timestamp).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </span>
      </div>
      {isOwn && (
        <Avatar
          src={message.avatar_url}
          alt={message.name}
          className="h-7 w-7 shrink-0"
        />
      )}
    </div>
  );
}
