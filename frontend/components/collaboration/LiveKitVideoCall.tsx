"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { 
  Video, 
  Mic, 
  MicOff, 
  Camera, 
  CameraOff, 
  Phone, 
  Users, 
  Share2, 
  Maximize2, 
  Minimize2,
  Settings,
  MessageSquare,
  Circle,
  MoreHorizontal,
  LayoutGrid,
  User,
  X,
  ChevronDown,
  ChevronUp
} from "lucide-react";
import { classNames, generateColor } from "@/lib/utils";

interface LiveKitVideoCallProps {
  roomName: string;
  participantName: string;
  participantIdentity: string;
  token: string;
  serverUrl: string;
  onLeave?: () => void;
  onError?: (error: Error) => void;
  className?: string;
}

interface Participant {
  identity: string;
  name: string;
  isLocal: boolean;
  hasVideo: boolean;
  hasAudio: boolean;
  videoEnabled: boolean;
  audioEnabled: boolean;
  screenShareEnabled: boolean;
  connectionQuality: "good" | "poor" | "lost";
  isSpeaking: boolean;
}

export function LiveKitVideoCall({
  roomName,
  participantName,
  participantIdentity,
  token,
  serverUrl,
  onLeave,
  onError,
  className,
}: LiveKitVideoCallProps) {
  const [participants, setParticipants] = useState<Map<string, Participant>>(new Map());
  const [localParticipant, setLocalParticipant] = useState<any>(null);
  const [isVideoEnabled, setIsVideoEnabled] = useState(true);
  const [isAudioEnabled, setIsAudioEnabled] = useState(true);
  const [isScreenSharing, setIsScreenSharing] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const [showParticipants, setShowParticipants] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [layout, setLayout] = useState<"grid" | "speaker">("grid");
  const [connectionState, setConnectionState] = useState<"connecting" | "connected" | "disconnected" | "reconnecting">("connecting");
  
  const roomRef = useRef<any>(null);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const remoteVideoRefs = useRef<Map<string, HTMLVideoElement>>(new Map());
  const messagesRef = useRef<Array<{ sender: string; content: string; timestamp: Date }>>([]);
  const [chatMessages, setChatMessages] = useState<Array<{ sender: string; content: string; timestamp: Date }>>([]);

  // Initialize LiveKit room
  useEffect(() => {
    // Dynamic import LiveKit client
    let isMounted = true;
    
    const initializeRoom = async () => {
      try {
        const LiveKit = await import('@livekit/client');
        const { Room, RoomEvent, Track, RemoteParticipant, TrackPublication } = LiveKit;

        const room = new Room({
          adaptiveStream: true,
          dynacast: true,
        });

        roomRef.current = room;

        // Set up event handlers
        room.on(RoomEvent.Connected, () => {
          if (!isMounted) return;
          console.log("[LiveKit] Connected to room:", roomName);
          setConnectionState("connected");
        });

        room.on(RoomEvent.Disconnected, () => {
          if (!isMounted) return;
          console.log("[LiveKit] Disconnected from room");
          setConnectionState("disconnected");
        });

        room.on(RoomEvent.ParticipantConnected, (participant) => {
          console.log("[LiveKit] Participant connected:", participant.identity);
          addRemoteParticipant(participant);
        });

        room.on(RoomEvent.ParticipantDisconnected, (participant) => {
          console.log("[LiveKit] Participant disconnected:", participant.identity);
          removeRemoteParticipant(participant.identity);
        });

        room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
          attachTrack(participant.identity, track);
        });

        room.on(RoomEvent.TrackUnsubscribed, (track, publication, participant) => {
          detachTrack(participant.identity, track);
        });

        room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
          updateSpeakingState(speakers);
        });

        room.on(RoomEvent.LocalTrackPublished, (publication) => {
          console.log("[LiveKit] Local track published:", publication.trackName);
        });

        room.on(RoomEvent.LocalTrackUnpublished, (publication) => {
          console.log("[LiveKit] Local track unpublished:", publication.trackName);
        });

        // Connect to room
        try {
          await room.connect(serverUrl, token);
          
          // Enable camera and microphone
          if (isVideoEnabled) {
            await room.localParticipant.setCameraEnabled(true);
          }
          await room.localParticipant.setMicrophoneEnabled(true);

          setConnectionState("connected");

          // Set up local participant
          setLocalParticipant({
            identity: participantIdentity,
            name: participantName,
            isLocal: true,
            hasVideo: true,
            hasAudio: true,
            videoEnabled: true,
            audioEnabled: true,
            screenShareEnabled: false,
            connectionQuality: "good",
            isSpeaking: false,
            color: generateColor(participantIdentity),
          });

          // Add existing remote participants
          room.remoteParticipants.forEach((participant) => {
            addRemoteParticipant(participant);
          });
        } catch (error) {
          console.error("[LiveKit] Failed to connect:", error);
          setConnectionState("disconnected");
          onError?.(error as Error);
        }
      };

      initializeRoom().catch(err => {
        if (isMounted) {
          setConnectionState("disconnected");
          onError?.(err);
        }
      });

      return () => {
        isMounted = false;
        if (roomRef.current) {
          roomRef.current.disconnect();
          roomRef.current = null;
        }
      };
    }, [roomName, participantName, participantIdentity, token, serverUrl, isVideoEnabled, isAudioEnabled]);

    const addRemoteParticipant = useCallback((participant: any) => {
      setParticipants(prev => {
        const newParticipants = new Map(prev);
        newParticipants.set(participant.identity, {
          identity: participant.identity,
          name: participant.name || participant.identity,
          isLocal: false,
          hasVideo: true,
          hasAudio: true,
          videoEnabled: true,
          audioEnabled: true,
          screenShareEnabled: false,
          connectionQuality: "good",
          isSpeaking: false,
          color: generateColor(participant.identity),
        });
        return newParticipants;
      });
    }, []);

    const removeRemoteParticipant = useCallback((identity: string) => {
      setParticipants(prev => {
        const newParticipants = new Map(prev);
        newParticipants.delete(identity);
        return newParticipants;
      });
    }, []);

    const attachTrack = useCallback((identity: string, track: any) => {
      // Track attachment handled by LiveKit's video elements
      console.log("[LiveKit] Track subscribed:", track.kind, "for", identity);
    }, []);

    const detachTrack = useCallback((identity: string, track: any) => {
      console.log("[LiveKit] Track unsubscribed:", track.kind, "for", identity);
    }, []);

    const updateSpeakingState = useCallback((speakers: any[]) => {
      setParticipants(prev => {
        const newParticipants = new Map(prev);
        speakers.forEach(speaker => {
          const participant = newParticipants.get(speaker.identity);
          if (participant) {
            newParticipants.set(speaker.identity, { ...participant, isSpeaking: true });
          }
        });
        // Reset speaking state for non-speakers
        newParticipants.forEach((participant, identity) => {
          if (!speakers.some(s => s.identity === identity)) {
            newParticipants.set(identity, { ...participant, isSpeaking: false });
          }
        });
        return { ...callState, participants: newParticipants };
      });
    }, []);

    // Media controls
    const toggleVideo = useCallback(async () => {
      if (!roomRef.current) return;
      const newValue = !isVideoEnabled;
      await roomRef.current.localParticipant.setCameraEnabled(newValue);
      setIsVideoEnabled(newValue);
      setLocalParticipant(prev => prev ? { ...prev, videoEnabled: newValue } : null);
    }, [isVideoEnabled]);

    const toggleAudio = useCallback(async () => {
      if (!roomRef.current) return;
      const newValue = !isAudioEnabled;
      await roomRef.current.localParticipant.setMicrophoneEnabled(newValue);
      setIsAudioEnabled(newValue);
      setLocalParticipant(prev => prev ? { ...prev, audioEnabled: newValue } : null);
    }, [isAudioEnabled]);

    const toggleScreenShare = useCallback(async () => {
      if (!roomRef.current) return;
      
      const newValue = !isScreenSharing;
      try {
        if (newValue) {
          // Start screen sharing
          const stream = await navigator.mediaDevices.getDisplayMedia({
            video: { cursor: "always" },
            audio: true,
          });
          
          await roomRef.current.localParticipant.setScreenShareEnabled(true);
          // In production, publish the screen share track
          
          setIsScreenSharing(true);
          setLocalParticipant(prev => prev ? { ...prev, screenShareEnabled: true } : null);
        } else {
          // Stop screen sharing
          await roomRef.current.localParticipant.setScreenShareEnabled(false);
          setIsScreenSharing(false);
          setLocalParticipant(prev => prev ? { ...prev, screenShareEnabled: false } : null);
        }
      } catch (error) {
        console.error('Screen share error:', error);
      }
    }, [isScreenSharing]);

    const toggleRecording = useCallback(async () => {
      const newValue = !isRecording;
      try {
        const response = await fetch(`/api/v1/realtime/calls/${callState.callId}/recording/${newValue ? 'start' : 'stop'}`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('access_token')}`,
          },
        });

        if (response.ok) {
          setIsRecording(newValue);
        }
      } catch (error) {
        console.error('Recording error:', error);
      }
    }, []);

    // Leave call
    const handleLeave = useCallback(() => {
      onLeave?.();
    }, [onLeave]);

    // Send chat message
    const sendChatMessage = useCallback((content: string) => {
      const message = {
        sender: participantIdentity,
        senderName: participantName,
        content,
        timestamp: new Date(),
      };
      messagesRef.current.push(message);
      setChatMessages([...messagesRef.current]);
    }, [participantIdentity, participantName]);

    // Cleanup on unmount
    useEffect(() => {
      return () => {
        if (roomRef.current) {
          roomRef.current.disconnect();
          roomRef.current = null;
        }
      }, []);

    const allParticipants = useMemo(() => {
      const participantsArray = Array.from(participants.values());
      if (localParticipant) {
        return [localParticipant, ...participantsArray.filter(p => !p.isLocal)];
      }
      return Array.from(participants.values());
    }, [participants, localParticipant]);

    // Layout logic
    const mainParticipant = layout === "speaker" 
      ? allParticipants.find(p => p.isSpeaking && !p.isLocal) || localParticipant
      : localParticipant;

    const otherParticipants = allParticipants.filter(p => p !== mainParticipant);

    return (
      <div className={classNames("flex h-full bg-background flex-col", className)}>
        {/* Connection Status Bar */}
        <div className={classNames(
          "flex items-center justify-between px-4 py-2 border-b border-line bg-canvas/80",
          connectionState === "connected" ? "bg-emerald-50" : 
          connectionState === "connecting" ? "bg-amber-50" : "bg-red-50"
        )}>
          <div className="flex items-center gap-3">
            <span className={classNames(
              "flex items-center gap-1.5 text-xs font-medium",
              connectionState === "connected" ? "text-emerald-700" :
              connectionState === "connecting" ? "text-amber-700" : "text-red-700"
            )}>
              <span className={classNames(
                "h-2 w-2 rounded-full",
                connectionState === "connected" ? "bg-emerald-500" :
                connectionState === "connecting" ? "bg-amber-500 animate-pulse" : "bg-red-500"
              )} />
              {connectionState.charAt(0).toUpperCase() + connectionState.slice(1)}
            </span>
            <span className="text-xs text-muted">|</span>
            <span className="text-sm font-medium">{roomName}</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted">
              {participants.size + 1} participant{participants.size !== 0 ? "s" : ""}
            </span>
          </div>
        </div>

        {/* Main Video Grid */}
        <div className="flex-1 flex overflow-hidden relative">
          {/* Main Video */}
          <div className={classNames(
            "relative flex-1 bg-black min-h-0",
            layout === "speaker" ? "flex-1" : ""
          )}>
            {/* Local Video */}
            <video
              ref={localVideoRef}
              autoPlay
              muted
              playsInline
              className={classNames(
                "w-full h-full object-cover",
                !isVideoEnabled && "hidden"
              )}
            />
            
            {/* Camera off placeholder */}
            {!isVideoEnabled && (
              <div className="absolute inset-0 flex items-center justify-center bg-black/80">
                <div className="text-center text-white">
                  <CameraOff className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <p className="text-lg font-medium">Camera Off</p>
                  <p className="text-sm opacity-70">Click camera button to enable</p>
                </div>
              </div>
            )}
            
            {/* Connection quality indicator */}
            {localParticipant && (
              <div className="absolute bottom-4 right-4">
                <span className={classNames(
                  "flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-black/70 text-white",
                  localParticipant.connectionQuality === "good" ? "bg-emerald-600" :
                  localParticipant.connectionQuality === "poor" ? "bg-amber-600" : "bg-red-600"
                )}>
                  {localParticipant.connectionQuality === "good" && "Excellent"}
                  {localParticipant.connectionQuality === "poor" && "Poor"}
                  {localParticipant.connectionQuality === "lost" && "Reconnecting..."}
                </span>
              </div>
            )}
            
            {/* Screen share indicator */}
            {isScreenSharing && (
              <div className="absolute top-4 left-4">
                <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-blue-600 text-white">
                  <Share2 className="h-3 w-3" />
                  Sharing Screen
                </span>
              </div>
            )}
            
            {/* Recording indicator */}
            {isRecording && (
              <div className="absolute top-4 right-4 animate-pulse">
                <span className="flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium bg-red-600 text-white">
                  <Circle className="h-3 w-3" />
                  REC
                </span>
              </div>
            )}
          </div>

          {/* Other Participants Grid (for grid layout) */}
          {layout === "grid" && otherParticipants.length > 0 && (
            <div className={classNames(
              "grid gap-2 p-2 bg-black/20",
              otherParticipants.length <= 1 ? "grid-cols-1" :
              otherParticipants.length <= 4 ? "grid-cols-2" :
              otherParticipants.length <= 9 ? "grid-cols-3" : "grid-cols-4"
            )}>
              {otherParticipants.map((participant) => (
                <div
                  key={participant.identity}
                  className="relative aspect-video bg-black rounded-lg overflow-hidden border border-line"
                >
                  <video
                    ref={(el) => { if (el) remoteVideoRefs.current.set(participant.identity, el); }}
                    autoPlay
                    playsInline
                    className="w-full h-full object-cover"
                  />
                  {!participant.videoEnabled && (
                    <div className="absolute inset-0 flex items-center justify-center bg-black/80">
                      <div className="text-center text-white">
                        <User className="h-12 w-12 mx-auto mb-2 opacity-50" />
                        <p className="text-sm font-medium">{participant.name}</p>
                        <p className="text-xs opacity-70">Camera Off</p>
                      </div>
                    </div>
                  )}
                  <div className="absolute bottom-2 left-2 right-2 flex items-center justify-between px-2 py-1 bg-black/70 text-white text-xs">
                    <span className="font-medium truncate">{participant.name}</span>
                    <div className="flex items-center gap-1">
                      {participant.isSpeaking && (
                        <span className="flex items-center gap-0.5 text-green-400 animate-pulse">
                          <span className="h-1.5 w-1.5 rounded-full bg-green-400" />
                        </span>
                      )}
                      {!participant.audioEnabled && (
                        <MicOff className="h-3 w-3 text-red-400" />
                      )}
                      {!participant.videoEnabled && (
                        <CameraOff className="h-3 w-3 text-red-400" />
                      )}
                      {participant.screenShareEnabled && (
                        <Share2 className="h-3 w-3 text-blue-400" />
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Sidebar - Chat & Participants */}
      <div className={classNames(
        "flex flex-col border-l border-line bg-canvas w-80 flex-shrink-0 transition-all duration-300",
        !showParticipants && "hidden"
      )}>
        <div className="flex items-center justify-between p-3 border-b border-line">
          <h3 className="font-medium text-sm">Participants ({allParticipants.length})</h3>
          <button
            onClick={() => setShowParticipants(false)}
            className="p-1 rounded hover:bg-muted transition-colors lg:hidden"
            aria-label="Close participants"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto p-3 space-y-2">
          {allParticipants.map((participant) => (
            <div
              key={participant.identity}
              className={classNames(
                "flex items-center gap-3 p-2 rounded-lg transition-colors",
                participant.isLocal ? "bg-brand-soft" : "hover:bg-muted"
              )}
            >
              <div className="relative w-8 h-8 flex-shrink-0">
                <div
                  className="w-full h-full rounded-full bg-muted flex items-center justify-center text-sm font-medium text-muted"
                  style={{ backgroundColor: participant.color }}
                >
                  {participant.name.charAt(0).toUpperCase()}
                </div>
                <span className={classNames(
                  "absolute bottom-0 right-0 h-2 w-2 rounded-full border-2 border-canvas",
                  participant.connectionQuality === "good" ? "bg-emerald-500" :
                  participant.connectionQuality === "poor" ? "bg-amber-500" : "bg-red-500"
                )} />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1">
                  <span className="text-sm font-medium truncate">
                    {participant.name} {participant.isLocal && "(You)"}
                  </span>
                  {participant.isSpeaking && (
                    <span className="flex items-center gap-0.5 text-green-500 text-xs animate-pulse">
                      <span className="h-1.5 w-1.5 rounded-full bg-green-500" />
                      Speaking
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 text-xs text-muted">
                  {!participant.audioEnabled && <MicOff className="h-3 w-3" />}
                  {!participant.videoEnabled && <CameraOff className="h-3 w-3" />}
                  {participant.screenShareEnabled && <Share2 className="h-3 w-3 text-blue-500" />}
                  <span className={classNames(
                    "px-1.5 py-0.5 rounded text-[10px] font-medium",
                    participant.connectionQuality === "good" ? "bg-emerald-100 text-emerald-700" :
                    participant.connectionQuality === "poor" ? "bg-amber-100 text-amber-700" : "bg-red-100 text-red-700"
                  )}>
                    {participant.connectionQuality}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Chat Sidebar */}
      {showChat && (
        <div className="flex flex-col border-l border-line bg-canvas w-80 flex-shrink-0">
          <div className="flex items-center justify-between p-3 border-b border-line">
            <h3 className="font-medium text-sm">Chat</h3>
            <button
              onClick={() => setShowChat(false)}
              className="p-1 rounded hover:bg-muted transition-colors lg:hidden"
              aria-label="Close chat"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {chatMessages.map((msg, index) => (
              <div key={index} className="flex flex-col gap-1">
                <div className="flex items-center gap-1">
                  <span className="text-xs font-medium text-brand">{msg.senderName}</span>
                  <span className="text-xs text-faint">{msg.timestamp.toLocaleTimeString()}</span>
                </div>
                <div className="text-sm text-ink">{msg.content}</div>
              </div>
            ))}
            <div ref={(el) => { el?.scrollIntoView({ behavior: "smooth" }); }} />
          </div>
          <div className="p-3 border-t border-line">
            <form onSubmit={(e) => { e.preventDefault(); const input = e.currentTarget.elements.namedItem("message") as HTMLInputElement; if (input.value.trim()) { sendChatMessage(input.value); input.value = ""; } }}>
              <div className="flex gap-2">
                <input
                  name="message"
                  type="text"
                  placeholder="Type a message..."
                  className="flex-1 h-9 px-3 rounded-lg border border-line bg-surface text-sm text-ink placeholder:text-faint focus:border-brand focus:outline-none focus:ring-1 focus:ring-brand"
                />
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-brand text-white text-sm font-medium hover:bg-brand-strong transition-colors"
                >
                  Send
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Control Bar */}
      <div className="flex items-center justify-center gap-3 px-6 py-4 border-t border-line bg-canvas/80 backdrop-blur-sm">
        <div className="flex items-center gap-2">
          {/* Mute/Unmute */}
          <button
            onClick={toggleAudio}
            className={classNames(
              "flex items-center justify-center w-12 h-12 rounded-full transition-colors",
              isAudioEnabled ? "bg-canvas hover:bg-muted" : "bg-red-100 text-red-600 hover:bg-red-200"
            )}
            aria-label={isAudioEnabled ? "Mute" : "Unmute"}
          >
            {isAudioEnabled ? <Mic className="h-5 w-5 text-ink" /> : <MicOff className="h-5 w-5 text-red-600" />}
          </button>

          {/* Video On/Off */}
          <button
            onClick={toggleVideo}
            className={classNames(
              "flex items-center justify-center w-12 h-12 rounded-full transition-colors",
              isVideoEnabled ? "bg-canvas hover:bg-muted" : "bg-red-100 text-red-600 hover:bg-red-200"
            )}
            aria-label={isVideoEnabled ? "Turn off camera" : "Turn on camera"}
          >
            {isVideoEnabled ? <Camera className="h-5 w-5 text-ink" /> : <CameraOff className="h-5 w-5 text-red-600" />}
          </button>

          {/* Screen Share */}
          <button
            onClick={toggleScreenShare}
            className={classNames(
              "flex items-center justify-center w-12 h-12 rounded-full transition-colors",
              isScreenSharing ? "bg-brand text-white" : "bg-canvas hover:bg-muted"
            )}
            aria-label={isScreenSharing ? "Stop sharing" : "Share screen"}
          >
            <Share2 className={classNames("h-5 w-5", isScreenSharing ? "text-white" : "text-ink")} />
          </button>

          {/* Recording */}
          <button
            onClick={toggleRecording}
            className={classNames(
              "flex items-center justify-center w-12 h-12 rounded-full transition-colors",
              isRecording ? "bg-red-100 text-red-600 animate-pulse" : "bg-canvas hover:bg-muted"
            )}
            aria-label={isRecording ? "Stop recording" : "Start recording"}
          >
            <Circle className={classNames("h-5 w-5", isRecording ? "text-red-600" : "text-ink")} />
          </button>
        </div>

        <div className="flex items-center gap-2">
          {/* Chat Toggle */}
          <button
            onClick={() => setShowChat(!showChat)}
            className={classNames(
              "flex items-center justify-center w-12 h-12 rounded-full transition-colors",
              showChat ? "bg-brand text-white" : "bg-canvas hover:bg-muted"
            )}
            aria-label={showChat ? "Close chat" : "Open chat"}
          >
            <MessageSquare className={classNames("h-5 w-5", showChat ? "text-white" : "text-ink")} />
          </button>

          {/* Participants Toggle */}
          <button
            onClick={() => setShowParticipants(!showParticipants)}
            className={classNames(
              "flex items-center justify-center w-12 h-12 rounded-full transition-colors",
              showParticipants ? "bg-brand text-white" : "bg-canvas hover:bg-muted"
            )}
            aria-label={showParticipants ? "Hide participants" : "Show participants"}
          >
            <Users className={classNames("h-5 w-5", showParticipants ? "text-white" : "text-ink")} />
          </button>

          {/* Layout Toggle */}
          <button
            onClick={() => setLayout(prev => prev === "grid" ? "speaker" : "grid")}
            className="flex items-center justify-center w-12 h-12 rounded-full transition-colors bg-canvas hover:bg-muted"
            aria-label={layout === "grid" ? "Speaker view" : "Grid view"}
          >
            <LayoutGrid className="h-5 w-5 text-ink" />
          </button>

          {/* Settings */}
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="flex items-center justify-center w-12 h-12 rounded-full transition-colors bg-canvas hover:bg-muted"
            aria-label="Settings"
          >
            <Settings className="h-5 w-5 text-ink" />
          </button>

          {/* Leave Call */}
          <button
            onClick={handleLeave}
            className="flex items-center justify-center w-12 h-12 rounded-full transition-colors bg-red-100 text-red-600 hover:bg-red-200"
            aria-label="Leave call"
          >
            <Phone className="h-5 w-5" />
          </button>
        </div>
      </div>
    </div>
  );
}

