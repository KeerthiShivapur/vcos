"use client";

import { useCallback, useEffect, useState } from "react";
import {
  getNativeBridge,
  initializeNativeBridge,
  NativeBridge,
} from "@/lib/native-bridge";

export interface NativeBridgeState {
  isReady: boolean;
  isNative: boolean;
  platform: string;
  pushToken: string | null;
  networkStatus: { connected: boolean; connectionType: string } | null;
  deviceInfo: any | null;
  error: string | null;
}

export interface UseNativeBridgeReturn extends NativeBridgeState {
  // Actions
  initialize: () => Promise<void>;
  requestPermissions: () => Promise<void>;
  getPushToken: () => Promise<string | null>;
  showLocalNotification: (
    title: string,
    body: string,
    data?: Record<string, any>,
  ) => Promise<void>;
  vibrate: (style?: "light" | "medium" | "heavy") => Promise<void>;
  showToast: (message: string, duration?: "short" | "long") => Promise<void>;
  share: (data: { title: string; text: string; url?: string }) => Promise<void>;
  copyToClipboard: (text: string) => Promise<void>;
  readFromClipboard: () => Promise<string>;
  openExternalUrl: (url: string) => Promise<void>;
  takePhoto: (options?: any) => Promise<string>;
  pickImages: (options?: any) => Promise<string[]>;
  getCurrentPosition: () => Promise<{ latitude: number; longitude: number }>;
  watchPosition: (
    callback: (pos: { latitude: number; longitude: number }) => void,
  ) => Promise<string>;
  clearWatch: (watchId: string) => Promise<void>;
  getDeviceInfo: () => Promise<any>;
  getNetworkStatus: () => Promise<{
    connected: boolean;
    connectionType: string;
  }>;
  writeFile: (path: string, data: string) => Promise<void>;
  readFile: (path: string) => Promise<string>;
  deleteFile: (path: string) => Promise<void>;
  listFiles: (path: string) => Promise<string[]>;
  startSpeechRecognition: (
    language: string,
    onResult: (text: string, isFinal: boolean) => void,
  ) => Promise<void>;
  stopSpeechRecognition: () => Promise<void>;
  speak: (text: string, lang?: string) => Promise<void>;
  stopSpeaking: () => Promise<void>;
  announceForAccessibility: (message: string) => Promise<void>;
  cleanup: () => Promise<void>;
}

export function useNativeBridge(): UseNativeBridgeReturn {
  const [bridge, setBridge] = useState<NativeBridge | null>(null);
  const [state, setState] = useState<NativeBridgeState>({
    isReady: false,
    isNative: false,
    platform: "web",
    pushToken: null,
    networkStatus: null,
    deviceInfo: null,
    error: null,
  });

  const initialize = useCallback(async () => {
    try {
      const nativeBridge = getNativeBridge({
        enablePushNotifications: true,
        enableBackgroundSync: true,
        enableHaptics: true,
        enableOfflineSupport: true,
      });

      await nativeBridge.initialize();
      setBridge(nativeBridge);

      // Get initial state
      const [platform, isNative, networkStatus, deviceInfo] = await Promise.all(
        [
          Promise.resolve(nativeBridge.getPlatform()),
          Promise.resolve(nativeBridge.isNative()),
          nativeBridge.getNetworkStatus().catch(() => null),
          nativeBridge.getDeviceInfo().catch(() => null),
        ],
      );

      setState((prev) => ({
        ...prev,
        isReady: true,
        isNative,
        platform,
        networkStatus,
        deviceInfo,
      }));
    } catch (error) {
      console.error("[useNativeBridge] Initialization failed:", error);
      setState((prev) => ({
        ...prev,
        error: error instanceof Error ? error.message : "Initialization failed",
        isReady: true,
      }));
    }
  }, []);

  useEffect(() => {
    initialize();
  }, [initialize]);

  const updateState = useCallback(async () => {
    if (!bridge) return;

    try {
      const [pushToken, networkStatus, deviceInfo] = await Promise.all([
        bridge.getPushToken().catch(() => null),
        bridge.getNetworkStatus().catch(() => null),
        bridge.getDeviceInfo().catch(() => null),
      ]);

      setState((prev) => ({
        ...prev,
        pushToken,
        networkStatus,
        deviceInfo,
      }));
    } catch (error) {
      console.error("[useNativeBridge] State update failed:", error);
    }
  }, [bridge]);

  // Update state periodically
  useEffect(() => {
    if (!bridge) return;

    const interval = setInterval(updateState, 30000);
    return () => clearInterval(interval);
  }, [bridge, updateState]);

  // Network status listener
  useEffect(() => {
    const handleOnline = () =>
      setState((prev) => ({
        ...prev,
        networkStatus: { connected: true, connectionType: "wifi" },
      }));
    const handleOffline = () =>
      setState((prev) => ({
        ...prev,
        networkStatus: { connected: false, connectionType: "none" },
      }));

    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);

    return () => {
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
    };
  }, []);

  return {
    ...state,
    initialize,
    requestPermissions:
      bridge?.requestPermissions.bind(bridge) ?? (async () => {}),
    getPushToken: bridge?.getPushToken.bind(bridge) ?? (async () => null),
    showLocalNotification:
      bridge?.showLocalNotification.bind(bridge) ?? (async () => {}),
    vibrate: bridge?.vibrate.bind(bridge) ?? (async () => {}),
    showToast: bridge?.showToast.bind(bridge) ?? (async () => {}),
    share: bridge?.share.bind(bridge) ?? (async () => {}),
    copyToClipboard: bridge?.copyToClipboard.bind(bridge) ?? (async () => {}),
    readFromClipboard:
      bridge?.readFromClipboard.bind(bridge) ?? (async () => ""),
    openExternalUrl: bridge?.openExternalUrl.bind(bridge) ?? (async () => {}),
    takePhoto: bridge?.takePhoto.bind(bridge) ?? (async () => ""),
    pickImages: bridge?.pickImages.bind(bridge) ?? (async () => []),
    getCurrentPosition:
      bridge?.getCurrentPosition.bind(bridge) ??
      (async () => ({ latitude: 0, longitude: 0 })),
    watchPosition: bridge?.watchPosition.bind(bridge) ?? (async () => ""),
    clearWatch: bridge?.clearWatch.bind(bridge) ?? (async () => {}),
    getDeviceInfo: bridge?.getDeviceInfo.bind(bridge) ?? (async () => null),
    getNetworkStatus:
      bridge?.getNetworkStatus.bind(bridge) ??
      (async () => ({ connected: true, connectionType: "wifi" })),
    writeFile: bridge?.writeFile.bind(bridge) ?? (async () => {}),
    readFile: bridge?.readFile.bind(bridge) ?? (async () => ""),
    deleteFile: bridge?.deleteFile.bind(bridge) ?? (async () => {}),
    listFiles: bridge?.listFiles.bind(bridge) ?? (async () => []),
    startSpeechRecognition:
      bridge?.startSpeechRecognition.bind(bridge) ?? (async () => {}),
    stopSpeechRecognition:
      bridge?.stopSpeechRecognition.bind(bridge) ?? (async () => {}),
    speak: bridge?.speak.bind(bridge) ?? (async () => {}),
    stopSpeaking: bridge?.stopSpeaking.bind(bridge) ?? (async () => {}),
    announceForAccessibility:
      bridge?.announceForAccessibility.bind(bridge) ?? (async () => {}),
    cleanup: bridge?.cleanup.bind(bridge) ?? (async () => {}),
  };
}

// Simplified hook for just push notifications
export function useNativePushNotifications() {
  const {
    pushToken,
    isNative,
    isReady,
    requestPermissions,
    getPushToken,
    showLocalNotification,
    error,
  } = useNativeBridge();

  const [permission, setPermission] =
    useState<NotificationPermission>("default");

  useEffect(() => {
    if (isReady) {
      Notification.requestPermission().then(setPermission);
    }
  }, [isReady]);

  const subscribe = useCallback(async () => {
    if (!isNative) return;
    await requestPermissions();
    const token = await getPushToken();
    return token;
  }, [isNative, requestPermissions, getPushToken]);

  return {
    isNative,
    isReady,
    permission,
    pushToken,
    error,
    subscribe,
    showLocalNotification,
  };
}
