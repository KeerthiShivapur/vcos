/**
 * Screen Sharing Hook
 * React hook for managing screen sharing using Browser Capture API
 */

import { useState, useCallback, useRef, useEffect } from 'react';

interface ScreenShareOptions {
  video?: boolean;
  audio?: boolean;
  preferCurrentTab?: boolean;
  selfBrowserSurface?: 'include' | 'exclude';
  systemAudio?: 'include' | 'exclude';
  surfaceSwitching?: 'include' | 'exclude';
  monitorTypeSurfaces?: 'include' | 'exclude';
}

interface ScreenShareState {
  isSharing: boolean;
  stream: MediaStream | null;
  error: string | null;
  tracks: {
    video: MediaStreamTrack | null;
    audio: MediaStreamTrack | null;
  };
}

interface UseScreenShareReturn extends ScreenShareState {
  startScreenShare: (options?: ScreenShareOptions) => Promise<MediaStream | null>;
  stopScreenShare: () => void;
  toggleScreenShare: (options?: ScreenShareOptions) => Promise<void>;
  replaceTrack: (track: MediaStreamTrack) => Promise<void>;
}

export function useScreenShare(): UseScreenShareReturn {
  const [state, setState] = useState<ScreenShareState>({
    isSharing: false,
    stream: null,
    error: null,
    tracks: { video: null, audio: null },
  });

  const streamRef = useRef<MediaStream | null>(null);
  const videoTrackRef = useRef<MediaStreamTrack | null>(null);
  const audioTrackRef = useRef<MediaStreamTrack | null>(null);

  // Handle stream end
  const handleTrackEnded = useCallback(() => {
    setState(prev => ({
      ...prev,
      isSharing: false,
      stream: null,
      tracks: { video: null, audio: null },
    }));
  }, []);

  const startScreenShare = useCallback(async (options: ScreenShareOptions = {}) => {
    try {
      setState(prev => ({ ...prev, error: null }));

      const {
        video = true,
        audio = true,
        preferCurrentTab = true,
        selfBrowserSurface = 'exclude',
        systemAudio = 'include',
        surfaceSwitching = 'include',
        monitorTypeSurfaces = 'include',
      } = options;

      // Check if getDisplayMedia is supported
      if (!navigator.mediaDevices?.getDisplayMedia) {
        throw new Error('Screen sharing not supported in this browser');
      }

      // Request screen capture
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: video ? {
          cursor: 'always',
          displaySurface: preferCurrentTab ? 'browser' : undefined,
          logicalSurface: true,
        } : false,
        audio: audio ? {
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        } : false,
        preferCurrentTab,
        selfBrowserSurface,
        systemAudio,
        surfaceSwitching,
        monitorTypeSurfaces,
      } as DisplayMediaStreamOptions);

      // Extract tracks
      const videoTrack = stream.getVideoTracks()[0] || null;
      const audioTrack = stream.getAudioTracks()[0] || null;

      // Handle track end
      if (videoTrack) {
        videoTrack.addEventListener('ended', () => {
          setState(prev => ({
            ...prev,
            isSharing: false,
            stream: null,
            tracks: { video: null, audio: null },
          }));
        });
      }

      if (audioTrack) {
        audioTrack.addEventListener('ended', () => {
          setState(prev => ({
            ...prev,
            tracks: { ...prev.tracks, audio: null },
          }));
          if (!stream.getVideoTracks().length) {
            setState(prev => ({ ...prev, isSharing: false, stream: null }));
          }
        });
      }

      // Update state
      setState({
        isSharing: true,
        stream,
        error: null,
        tracks: { video: videoTrack, audio: audioTrack },
      });

      // Store refs
      if (videoTrack) videoTrackRef.current = videoTrack;
      if (audioTrack) audioTrackRef.current = audioTrack;
      streamRef.current = stream;

      return stream;
    } catch (error) {
      setState(prev => ({ ...prev, error: error instanceof Error ? error.message : 'Screen sharing failed' }));
      return null;
    }
  }, []);

  const stopScreenShare = useCallback(() => {
    if (state.stream) {
      state.stream.getTracks().forEach(track => {
        track.stop();
      });
    }
    
    if (videoTrackRef.current) {
      videoTrackRef.current.removeEventListener('ended', () => {});
      videoTrackRef.current = null;
    }
    
    if (audioTrackRef.current) {
      audioTrackRef.current.removeEventListener('ended', () => {});
      audioTrackRef.current = null;
    }
    
    if (streamRef.current) {
      streamRef.current = null;
    }

    setState({
      isSharing: false,
      stream: null,
      error: null,
      tracks: { video: null, audio: null },
    });
  }, []);

  const toggleScreenShare = useCallback(async (options?: ScreenShareOptions) => {
    if (state.isSharing) {
      stopScreenShare();
    } else {
      await startScreenShare(options);
    }
  }, [state.isSharing]);

  const replaceTrack = useCallback(async (newTrack: MediaStreamTrack) => {
    // In a real implementation, this would replace the track in the WebRTC peer connection
    // For now, we just update the local stream
    if (state.stream) {
      const newStream = new MediaStream();
      
      // Add all existing tracks except the one being replaced
      state.stream.getTracks().forEach(track => {
        if (track.kind !== newTrack.kind) {
          newStream.addTrack(track.clone());
        }
      });
      
      // Add the new track
      newStream.addTrack(newTrack);
      
      setState(prev => ({
        ...prev,
        stream: newStream,
        tracks: {
          video: newTrack.kind === 'video' ? newTrack : prev.tracks.video,
          audio: newTrack.kind === 'audio' ? newTrack : prev.tracks.audio
        }
      }));
    }
  }, [state.stream]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (state.isSharing) {
        stopScreenShare();
      }
    };
  }, [state.isSharing]);

  return {
    isSharing: state.isSharing,
    stream: state.stream,
    error: state.error,
    tracks: state.tracks,
    startScreenShare,
    stopScreenShare,
    toggleScreenShare,
    replaceTrack,
  };
}

// Hook for managing screen share in a call context
export function useCallScreenShare(callId: string) {
  const [isSharing, setIsSharing] = useState(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [error, setError] = useState<string | null>(null);

  const startScreenShare = useCallback(async (callId: string, options = {}) => {
    try {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { cursor: 'always' },
        audio: true,
        preferCurrentTab: true,
        selfBrowserSurface: 'exclude',
        systemAudio: 'include',
        surfaceSwitching: 'include',
        monitorTypeSurfaces: 'include',
      });

      setStream(stream);
      setIsSharing(true);
      setError(null);

      // Notify call server about screen share start
      await fetch(`/api/v1/realtime/calls/${callId}/screen-share/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ streamId: stream.id }),
      });

      return stream;
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Failed to start screen share');
      return null;
    }
  }, []);

  const stopScreenShare = useCallback(() => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      setStream(null);
      setIsSharing(false);
      
      // Notify call server about screen share end
      fetch(`/api/v1/realtime/calls/${callId}/screen-share/stop`, {
        method: 'POST',
      }).catch(console.error);
    }
  }, [stream, callId]);

  return {
    isSharing,
    stream,
    error,
    startScreenShare,
    stopScreenShare,
  };
}