/**
 * WebRTC Call Hook
 * React hook for managing WebRTC voice/video calls with LiveKit integration
 */

import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useAuth } from './useAuth';

export interface CallParticipant {
  identity: string;
  name: string;
  isLocal: boolean;
  hasVideo: boolean;
  hasAudio: boolean;
  videoEnabled: boolean;
  audioEnabled: boolean;
  screenShareEnabled: boolean;
  connectionQuality: 'good' | 'poor' | 'lost';
  isSpeaking: boolean;
  color?: string;
}

export type CallState = 'idle' | 'connecting' | 'ringing' | 'connecting' | 'connected' | 'hold' | 'ended' | 'failed' | 'rejected';

export interface CallOptions {
  callType: 'audio' | 'video' | 'screen_share' | 'conference';
  targetUsers: string[];
  settings?: Record<string, any>;
}

export interface CallState {
  callId: string;
  callType: 'audio' | 'video' | 'screen_share' | 'conference';
  state: CallState;
  participants: Map<string, CallParticipant>;
  localParticipant: CallParticipant | null;
  isVideoEnabled: boolean;
  isAudioEnabled: boolean;
  isScreenSharing: boolean;
  isRecording: boolean;
  connectionState: 'connecting' | 'connected' | 'disconnected' | 'reconnecting';
  livekitRoom: string | null;
  livekitToken: string | null;
  recordingId: string | null;
}

export function useCall(options: { organizationId: string } = { organizationId: '' }) {
  const { user, accessToken } = useAuth();
  const [callState, setCallState] = useState<CallState>({
    callId: '',
    callType: 'video',
    state: 'idle',
    participants: new Map(),
    localParticipant: null,
    isVideoEnabled: true,
    isAudioEnabled: true,
    isScreenSharing: false,
    isRecording: false,
    connectionState: 'connecting',
    livekitRoom: null,
    livekitToken: null,
    recordingId: null,
  });

  const roomRef = useRef<any>(null);
  const localVideoRef = useRef<HTMLVideoElement>(null);
  const remoteVideoRefs = useRef<Map<string, HTMLVideoElement>>(new Map());
  const messagesRef = useRef<Array<{ sender: string; content: string; timestamp: Date }>>([]);
  const [chatMessages, setChatMessages] = useState<Array<{ sender: string; content: string; timestamp: Date }>>([]);

  // Initialize call
  const initiateCall = useCallback(async (callOptions: CallOptions) => {
    const { callType, targetUsers, settings } = callOptions;

    try {
      // Call backend to initiate call
      const response = await fetch('/api/v1/realtime/calls', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          call_type: callType,
          target_users: targetUsers,
          settings,
          user_name: user?.full_name || user?.email,
          user_color: '#6366f1',
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to initiate call');
      }

      const result = await response.json();
      
      setCallState(prev => ({
        ...prev,
        callId: result.call_id,
        callType,
        state: 'initiated',
        livekitRoom: result.livekit_room,
        participants: new Map([
          [user.id, {
            identity: user.id,
            name: user?.full_name || user?.email || 'You',
            isLocal: true,
            hasVideo: callType !== 'audio',
            hasAudio: true,
            videoEnabled: callType !== 'audio',
            audioEnabled: true,
            screenShareEnabled: false,
            connectionQuality: 'good',
            isSpeaking: false,
            color: '#6366f1',
          }],
          ...targetUsers.map(u => [u, {
            identity: u,
            name: '', // Will be filled when they join
            isLocal: false,
            hasVideo: callType !== 'audio',
            hasAudio: true,
            videoEnabled: callType !== 'audio',
            audioEnabled: true,
            screenShareEnabled: false,
            connectionQuality: 'good',
            isSpeaking: false,
            color: '#6366f1',
          }]),
        ]),
        localParticipant: {
          identity: user.id,
          name: user?.full_name || user?.email || 'You',
          isLocal: true,
          hasVideo: callType !== 'audio',
          hasAudio: true,
          videoEnabled: callType !== 'audio',
          audioEnabled: true,
          screenShareEnabled: false,
          connectionQuality: 'good',
          isSpeaking: false,
          color: '#6366f1',
        },
        isVideoEnabled: callType !== 'audio',
        isAudioEnabled: true,
        isScreenSharing: false,
        isRecording: false,
        connectionState: 'connecting',
        livekitRoom: result.livekit_room,
        livekitToken: result.livekit_token,
      }));

      // Initialize LiveKit if configured
      if (result.livekit_token && result.livekit_room) {
        await initializeLiveKit(result.livekit_room, result.livekit_token);
      }

      return result;
    } catch (error) {
      console.error('Failed to initiate call:', error);
      throw error;
    }
  }, [accessToken, user]);

  // Initialize LiveKit room
  const initializeLiveKit = useCallback(async (roomName: string, token: string) => {
    try {
      // Dynamic import LiveKit client
      const LiveKit = await import('@livekit/client');
      const { Room, RoomEvent, Track, RemoteParticipant } = LiveKit;

      const room = new Room({
        adaptiveStream: true,
        dynacast: true,
      });

      roomRef.current = room;

      // Set up event handlers
      room.on(RoomEvent.Connected, () => {
        console.log('[LiveKit] Connected to room');
        setCallState(prev => ({ ...prev, connectionState: 'connected', state: 'connected' }));
      });

      room.on(RoomEvent.Disconnected, () => {
        console.log('[LiveKit] Disconnected from room');
        setCallState(prev => ({ ...prev, connectionState: 'disconnected' }));
      });

      room.on(RoomEvent.ParticipantConnected, (participant) => {
        console.log('[LiveKit] Participant connected:', participant.identity);
        addRemoteParticipant(participant);
      });

      room.on(RoomEvent.ParticipantDisconnected, (participant) => {
        console.log('[LiveKit] Participant disconnected:', participant.identity);
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

      // Connect to room
      await room.connect(serverUrl, token);
      
      // Enable camera and microphone
      if (callState.isVideoEnabled) {
        await room.localParticipant.setCameraEnabled(true);
      }
      await room.localParticipant.setMicrophoneEnabled(true);

      setCallState(prev => ({
        ...prev,
        connectionState: 'connected',
        state: 'connected',
      }));

    } catch (error) {
      console.error('[LiveKit] Failed to initialize:', error);
      setCallState(prev => ({ ...prev, connectionState: 'disconnected' }));
    }
  }, []);

  const addRemoteParticipant = useCallback((participant: any) => {
    setCallState(prev => {
      const newParticipants = new Map(prev.participants);
      newParticipants.set(participant.identity, {
        identity: participant.identity,
        name: participant.name || participant.identity,
        isLocal: false,
        hasVideo: true,
        hasAudio: true,
        videoEnabled: true,
        audioEnabled: true,
        screenShareEnabled: false,
        connectionQuality: 'good',
        isSpeaking: false,
        color: generateColor(participant.identity),
      });
      return { ...prev, participants: newParticipants };
    });
  }, []);

  const removeRemoteParticipant = useCallback((identity: string) => {
    setCallState(prev => {
      const newParticipants = new Map(prev.participants);
      newParticipants.delete(identity);
      return { ...prev, participants: newParticipants };
    });
  }, []);

  const attachTrack = useCallback((identity: string, track: any) => {
    // Track attachment handled by LiveKit's video elements
    console.log('[LiveKit] Track subscribed:', track.kind, 'for', identity);
  }, []);

  const detachTrack = useCallback((identity: string, track: any) => {
    console.log('[LiveKit] Track unsubscribed:', track.kind, 'for', identity);
  }, []);

  const updateSpeakingState = useCallback((speakers: any[]) => {
    setCallState(prev => {
      const newParticipants = new Map(prev.participants);
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
      return { ...prev, participants: newParticipants };
    });
  }, []);

  // Media controls
  const toggleVideo = useCallback(async () => {
    if (!roomRef.current) return;
    const newValue = !callState.isVideoEnabled;
    await roomRef.current.localParticipant.setCameraEnabled(newValue);
    setCallState(prev => ({
      ...prev,
      isVideoEnabled: newValue,
      localParticipant: prev.localParticipant ? { ...prev.localParticipant, videoEnabled: newValue } : null,
    }));
  }, []);

  const toggleAudio = useCallback(async () => {
    if (!roomRef.current) return;
    const newValue = !callState.isAudioEnabled;
    await roomRef.current.localParticipant.setMicrophoneEnabled(newValue);
    setCallState(prev => ({
      ...prev,
      isAudioEnabled: newValue,
      localParticipant: prev.localParticipant ? { ...prev.localParticipant, audioEnabled: newValue } : null,
    }));
  }, []);

  const toggleScreenShare = useCallback(async () => {
    if (!roomRef.current) return;
    
    const newValue = !callState.isScreenSharing;
    try {
      if (newValue) {
        // Start screen sharing
        const stream = await navigator.mediaDevices.getDisplayMedia({
          video: { cursor: 'always' },
          audio: true,
        });
        
        await roomRef.current.localParticipant.setScreenShareEnabled(true);
        // In production, publish the screen share track
        
        setCallState(prev => ({
          ...prev,
          isScreenSharing: true,
          localParticipant: prev.localParticipant ? { ...prev.localParticipant, screenShareEnabled: true } : null,
        }));
      } else {
        // Stop screen sharing
        await roomRef.current.localParticipant.setScreenShareEnabled(false);
        setCallState(prev => ({
          ...prev,
          isScreenSharing: false,
          localParticipant: prev.localParticipant ? { ...prev.localParticipant, screenShareEnabled: false } : null,
        }));
      }
    } catch (error) {
      console.error('Screen share error:', error);
    }
  }, []);

  const toggleRecording = useCallback(async () => {
    const newValue = !callState.isRecording;
    try {
      const response = await fetch(`/api/v1/realtime/calls/${callState.callId}/recording/${newValue ? 'start' : 'stop'}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });

      if (response.ok) {
        setCallState(prev => ({ ...prev, isRecording: newValue }));
      }
    } catch (error) {
      console.error('Recording error:', error);
    }
  }, [callState.callId, callState.isRecording, accessToken]);

  // Accept incoming call
  const acceptCall = useCallback(async (callId: string) => {
    try {
      const response = await fetch(`/api/v1/realtime/calls/${callId}/accept`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
        body: JSON.stringify({
          media_state: {
            audio: true,
            video: true,
            screen_share: false,
          },
        }),
      });

      if (!response.ok) throw new Error('Failed to accept call');

      const result = await response.json();
      setCallState(prev => ({ ...prev, callId, livekitRoom: result.livekit_room, livekitToken: result.livekit_token }));
      
      if (result.livekit_token && result.livekit_room) {
        await initializeLiveKit(result.livekit_room, result.livekit_token);
      }

      return result;
    } catch (error) {
      console.error('Failed to accept call:', error);
      throw error;
    }
  }, [accessToken]);

  // Reject call
  const rejectCall = useCallback(async (callId: string) => {
    try {
      await fetch(`/api/v1/realtime/calls/${callId}/reject`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
      });
    } catch (error) {
      console.error('Failed to reject call:', error);
    }
  }, [accessToken]);

  // End call
  const endCall = useCallback(async () => {
    if (!callState.callId) return;

    try {
      await fetch(`/api/v1/realtime/calls/${callState.callId}/end`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
        },
      });
    } catch (error) {
      console.error('Failed to end call:', error);
    }

    // Cleanup
    if (roomRef.current) {
      roomRef.current.disconnect();
      roomRef.current = null;
    }

    setCallState(prev => ({
      ...prev,
      state: 'ended',
      connectionState: 'disconnected',
      participants: new Map(),
      localParticipant: null,
    }));
  }, [callState.callId, accessToken]);

  // Toggle mute
  const toggleMute = useCallback(async () => {
    if (!roomRef.current) return;
    const newValue = !callState.isAudioEnabled;
    await roomRef.current.localParticipant.setMicrophoneEnabled(newValue);
    setCallState(prev => ({
      ...prev,
      isAudioEnabled: newValue,
      localParticipant: prev.localParticipant ? { ...prev.localParticipant, audioEnabled: newValue } : null,
    }));
  }, []);

  // Toggle video
  const toggleVideo = useCallback(async () => {
    if (!roomRef.current) return;
    const newValue = !callState.isVideoEnabled;
    await roomRef.current.localParticipant.setCameraEnabled(newValue);
    setCallState(prev => ({
      ...prev,
      isVideoEnabled: newValue,
      localParticipant: prev.localParticipant ? { ...prev.localParticipant, videoEnabled: newValue } : null,
    }));
  }, []);

  // Toggle screen share
  const toggleScreenShare = useCallback(async () => {
    if (!roomRef.current) return;
    const newValue = !callState.isScreenSharing;
    
    try {
      if (newValue) {
        // Screen share is handled by LiveKit's setScreenShareEnabled
        await roomRef.current.localParticipant.setScreenShareEnabled(true);
      } else {
        await roomRef.current.localParticipant.setScreenShareEnabled(false);
      }
      setCallState(prev => ({
        ...prev,
        isScreenSharing: newValue,
        localParticipant: prev.localParticipant ? { ...prev.localParticipant, screenShareEnabled: newValue } : null,
      }));
    } catch (error) {
      console.error('Screen share error:', error);
    }
  }, []);

  // Toggle recording
  const toggleRecording = useCallback(async () => {
    await toggleRecording();
  }, []);

  // Leave call
  const leaveCall = useCallback(async () => {
    await endCall();
  }, []);

  // Chat
  const sendChatMessage = useCallback((content: string) => {
    const message = {
      sender: user.id,
      senderName: user?.full_name || user?.email,
      content,
      timestamp: new Date(),
    };
    messagesRef.current.push(message);
    setChatMessages(prev => [...prev, message]);
  }, [user]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect();
        roomRef.current = null;
      }
    }, []);

  const allParticipants = useMemo(() => {
    const participants = callState.localParticipant 
      ? [callState.localParticipant, ...Array.from(callState.participants.values()).filter(p => !p.isLocal)]
      : Array.from(callState.participants.values());
    return participants;
  }, [callState.participants, callState.localParticipant]);

  return {
    ...callState,
    participants: Array.from(callState.participants.values()),
    allParticipants,
    initiateCall,
    acceptCall,
    rejectCall: useCallback(async (callId: string) => {
      await fetch(`/api/v1/realtime/calls/${callId}/reject`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${accessToken}` },
      });
    }, [accessToken]),
    endCall,
    leaveCall,
    toggleMute: useCallback(() => {
      setCallState(prev => ({
        ...prev,
        isAudioEnabled: !prev.isAudioEnabled,
        localParticipant: prev.localParticipant ? { ...prev.localParticipant, audioEnabled: !prev.localParticipant.audioEnabled } : null,
      }));
      // Actual mute handled by LiveKit
      if (roomRef.current) {
        roomRef.current.localParticipant.setMicrophoneEnabled(!callState.isAudioEnabled);
      }
    }, []),
    toggleVideo,
    toggleScreenShare,
    toggleRecording,
    toggleMute,
    toggleVideo,
    toggleScreenShare,
    sendChatMessage,
    chatMessages,
    mainParticipant: callState.localParticipant,
    otherParticipants: Array.from(callState.participants.values()).filter(p => !p.isLocal),
    generateColor,
  };
}

// Helper functions
function generateColor(id: string): string {
  const colors = [
    "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFBE0B", "#FB5607",
    "#8338EC", "#3A86FF", "#06D6A0", "#FF9F1C", "#FF6F61",
  ];
  let hash = 0;
  for (let i = 0; i < id.length; i++) {
    hash = (hash * 31 + id.charCodeAt(i)) >>> 0;
  }
  return colors[hash % colors.length];
}

// Hook for managing incoming calls
export function useIncomingCalls() {
  const { user, accessToken } = useAuth();
  const [incomingCalls, setIncomingCalls] = useState<Array<{
    callId: string;
    callerId: string;
    callerName: string;
    callType: string;
    timestamp: number;
  }>([]);

  useEffect(() => {
    // In production, this would listen for incoming call events via WebSocket
    // For now, we'll poll or use WebSocket events
    return () => {};
  }, []);

  return {
    incomingCalls,
    acceptCall: useCallback(async (callId: string) => {
      const response = await fetch(`/api/v1/realtime/calls/${callId}/accept`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${accessToken}`,
        },
      });
      return response.json();
    }, []),
    rejectCall: useCallback(async (callId: string) => {
      await fetch(`/api/v1/realtime/calls/${callId}/reject`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${accessToken}` },
      });
    }, [accessToken]),
  };
}

// Hook for screen sharing using Browser Capture API
export function useScreenShare() {
  const [isSharing, setIsSharing] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startScreenShare = useCallback(async (options: {
    video?: boolean;
    audio?: boolean;
    preferCurrentTab?: boolean;
  } = {}) => {
    try {
      setError(null);
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: options.video !== false,
        audio: options.audio !== false,
        preferCurrentTab: options.preferCurrentTab ?? true,
        selfBrowserSurface: 'exclude',
        systemAudio: 'include',
        surfaceSwitching: 'include',
      });

      setStream(stream);
      setIsSharing(true);

      // Handle stream end
      stream.getVideoTracks()[0]?.addEventListener('ended', () => {
        setIsSharing(false);
        setStream(null);
      });

      return stream;
    } catch (error) {
      const err = error as Error;
      if (err.name === 'NotAllowedError') {
        setError('Screen sharing permission denied');
      } else if (err.name === 'NotFoundError') {
        setError('No screen available to share');
      } else {
        setError(err.message);
      }
      throw error;
    }, []);

  const stopScreenShare = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      setStream(null);
      setIsSharing(false);
    }
  }, [stream]);

  return {
    isSharing,
    stream,
    error,
    startScreenShare,
    stopScreenShare,
  };
}

// Hook for managing call UI state
export function useCallUI() {
  const [showChat, setShowChat] = useState(false);
  const [showParticipants, setShowParticipants] = useState(true);
  const [showSettings, setShowSettings] = useState(false);
  const [showChatInput, setShowChatInput] = useState(false);
  const [layout, setLayout] = useState<'grid' | 'speaker'>('grid');
  const [chatInput, setChatInput] = useState('');

  const toggleChat = useCallback(() => setShowChat(!showChat), [showChat]);
  const toggleParticipants = useCallback(() => setShowParticipants(!showParticipants), [showParticipants]);
  const toggleSettings = useCallback(() => setShowSettings(!showSettings), [showSettings]);
  const toggleLayout = useCallback(() => setLayout(prev => prev === 'grid' ? 'speaker' : 'grid'), []);

  return {
    showChat,
    showParticipants,
    showSettings,
    showChatInput,
    layout,
    chatInput,
    setChatInput,
    toggleChat,
    toggleParticipants,
    toggleSettings,
    toggleLayout,
  };
}