/**
 * VCOS Native Bridge for Capacitor
 * Provides native functionality for iOS and Android
 */

import { Capacitor } from "@capacitor/core";
import {
  PushNotifications,
  PushNotificationSchema,
  PushNotificationActionPerformed,
} from "@capacitor/push-notifications";
import {
  LocalNotifications,
  LocalNotificationSchema,
} from "@capacitor/local-notifications";
import { BackgroundTask } from "@capacitor/background-task";
import { Network } from "@capacitor/network";
import { Device } from "@capacitor/device";
import { App } from "@capacitor/app";
import { Haptics, ImpactStyle } from "@capacitor/haptics";
import { StatusBar, Style } from "@capacitor/status-bar";
import { SplashScreen } from "@capacitor/splash-screen";
import { Keyboard } from "@capacitor/keyboard";
import { Browser } from "@capacitor/browser";
import { Share } from "@capacitor/share";
import { Clipboard } from "@capacitor/clipboard";
import { Filesystem, Directory } from "@capacitor/filesystem";
import { Geolocation } from "@capacitor/geolocation";
import { Camera, CameraResultType, CameraSource } from "@capacitor/camera";
import { ImagePicker } from "@capacitor/image-picker";
import { Media } from "@capacitor/media";
import { Motion } from "@capacitor/motion";
import { Orientation } from "@capacitor/orientation";
import { ScreenReader } from "@capacitor/screen-reader";
import { SpeechRecognition } from "@capacitor/speech-recognition";
import { TextToSpeech } from "@capacitor/text-to-speech";
import { Toast } from "@capacitor/toast";

export interface NativeBridgeConfig {
  enablePushNotifications: boolean;
  enableBackgroundSync: boolean;
  enableHaptics: boolean;
  enableOfflineSupport: boolean;
}

class NativeBridge {
  private config: NativeBridgeConfig;
  private initialized = false;
  private pushToken: string | null = null;
  private backgroundSyncInterval: NodeJS.Timeout | null = null;

  constructor(
    config: NativeBridgeConfig = {
      enablePushNotifications: true,
      enableBackgroundSync: true,
      enableHaptics: true,
      enableOfflineSupport: true,
    },
  ) {
    this.config = config;
  }

  async initialize(): Promise<void> {
    if (this.initialized) return;

    if (!Capacitor.isNativePlatform()) {
      console.log(
        "[NativeBridge] Not running on native platform, skipping native initialization",
      );
      return;
    }

    try {
      // Initialize core plugins
      await this.initializeCorePlugins();

      // Initialize push notifications
      if (this.config.enablePushNotifications) {
        await this.initializePushNotifications();
      }

      // Initialize background sync
      if (this.config.enableBackgroundSync) {
        await this.initializeBackgroundSync();
      }

      // Initialize haptics
      if (this.config.enableHaptics) {
        await this.initializeHaptics();
      }

      // Initialize offline support
      if (this.config.enableOfflineSupport) {
        await this.initializeOfflineSupport();
      }

      this.initialized = true;
      console.log("[NativeBridge] Initialized successfully");
    } catch (error) {
      console.error("[NativeBridge] Initialization failed:", error);
      throw error;
    }
  }

  private async initializeCorePlugins(): Promise<void> {
    // Status bar
    await StatusBar.setStyle({ style: Style.Dark });
    await StatusBar.setBackgroundColor({ color: "#6366f1" });

    // Splash screen
    await SplashScreen.hide();

    // Keyboard
    Keyboard.addListener("keyboardWillShow", () => {
      document.body.classList.add("keyboard-open");
    });
    Keyboard.addListener("keyboardWillHide", () => {
      document.body.classList.remove("keyboard-open");
    });

    // App lifecycle
    App.addListener("appStateChange", ({ isActive }) => {
      console.log("[NativeBridge] App state changed:", isActive);
      if (isActive) {
        // App came to foreground - trigger sync
        this.triggerBackgroundSync();
      }
    });

    // Network monitoring
    Network.addListener("networkStatusChange", (status) => {
      console.log("[NativeBridge] Network status:", status);
      if (status.connected) {
        this.triggerBackgroundSync();
      }
    });
  }

  private async initializePushNotifications(): Promise<void> {
    // Request permissions
    const permResult = await PushNotifications.requestPermissions();

    if (permResult.receive === "granted") {
      // Register with FCM/APNs
      await PushNotifications.register();

      // Listen for registration
      PushNotifications.addListener("registration", (token) => {
        this.pushToken = token.value;
        console.log("[NativeBridge] Push token:", token.value);
        this.sendTokenToServer(token.value);
      });

      PushNotifications.addListener("registrationError", (error) => {
        console.error("[NativeBridge] Push registration error:", error);
      });

      // Handle push notification received
      PushNotifications.addListener(
        "pushNotificationReceived",
        (notification: PushNotificationSchema) => {
          console.log("[NativeBridge] Push received:", notification);
          this.handlePushNotification(notification);
        },
      );

      // Handle push notification action
      PushNotifications.addListener(
        "pushNotificationActionPerformed",
        (action: PushNotificationActionPerformed) => {
          console.log("[NativeBridge] Push action:", action);
          this.handlePushAction(action);
        },
      );
    }
  }

  private async initializeBackgroundSync(): Promise<void> {
    // Register background task
    await BackgroundTask.enable();

    BackgroundTask.addListener("backgroundTask", async () => {
      console.log("[NativeBridge] Background task triggered");
      await this.performBackgroundSync();
    });

    // Schedule periodic background sync
    this.backgroundSyncInterval = setInterval(
      () => {
        if (navigator.onLine) {
          this.triggerBackgroundSync();
        }
      },
      30 * 60 * 1000,
    ); // Every 30 minutes
  }

  private async initializeHaptics(): Promise<void> {
    // Haptics are available by default
    console.log("[NativeBridge] Haptics initialized");
  }

  private async initializeOfflineSupport(): Promise<void> {
    // Network listener already set up in initializeCorePlugins
    console.log("[NativeBridge] Offline support initialized");
  }

  private async triggerBackgroundSync(): Promise<void> {
    if (!this.config.enableBackgroundSync) return;

    try {
      await BackgroundTask.beforeExit();
      await this.performBackgroundSync();
      await BackgroundTask.finish();
    } catch (error) {
      console.error("[NativeBridge] Background sync failed:", error);
    }
  }

  private async performBackgroundSync(): Promise<void> {
    console.log("[NativeBridge] Performing background sync");

    // Notify web layer to sync
    if (window.webkit && window.webkit.messageHandlers) {
      window.webkit.messageHandlers.backgroundSync.postMessage({});
    }

    // Also dispatch custom event for React layer
    window.dispatchEvent(new CustomEvent("backgroundSync"));
  }

  private async sendTokenToServer(token: string): Promise<void> {
    try {
      await fetch("/api/v1/push/token", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${localStorage.getItem("accessToken")}`,
        },
        body: JSON.stringify({ token, platform: Capacitor.getPlatform() }),
      });
    } catch (error) {
      console.error("[NativeBridge] Failed to send token to server:", error);
    }
  }

  private handlePushNotification(notification: PushNotificationSchema): void {
    // Forward to web layer
    window.dispatchEvent(
      new CustomEvent("pushNotification", {
        detail: notification,
      }),
    );

    // Show local notification if app is in foreground
    if (document.visibilityState === "visible") {
      this.showLocalNotification(notification);
    }
  }

  private handlePushAction(action: PushNotificationActionPerformed): void {
    const { actionId, notification } = action;

    // Handle action
    switch (actionId) {
      case "open":
        // Navigate to relevant page
        if (notification.data?.url) {
          window.location.href = notification.data.url;
        }
        break;
      case "dismiss":
        // Just dismiss
        break;
      default:
        // Custom action
        window.dispatchEvent(
          new CustomEvent("pushAction", {
            detail: { actionId, notification },
          }),
        );
    }
  }

  private showLocalNotification(notification: PushNotificationSchema): void {
    // Create a local notification for foreground display
    LocalNotifications.schedule({
      notifications: [
        {
          id: Date.now(),
          title: notification.title || "VCOS",
          body: notification.body || "",
          extra: notification.data,
          smallIcon: "ic_stat_icon_config_sample",
          iconColor: "#6366f1",
        },
      ],
    });
  }

  // ==================== Public API ====================

  async getPushToken(): Promise<string | null> {
    if (!this.initialized) await this.initialize();
    return this.pushToken;
  }

  async showLocalNotification(
    title: string,
    body: string,
    data?: Record<string, any>,
  ): Promise<void> {
    await LocalNotifications.schedule({
      notifications: [
        {
          id: Date.now(),
          title,
          body,
          extra: data,
          smallIcon: "ic_stat_icon_config_sample",
          iconColor: "#6366f1",
        },
      ],
    });
  }

  async vibrate(style: ImpactStyle = "medium"): Promise<void> {
    if (this.config.enableHaptics) {
      await Haptics.impact({ style });
    }
  }

  async showToast(
    message: string,
    duration: "short" | "long" = "short",
  ): Promise<void> {
    await Toast.show({ text: message, duration });
  }

  async share(data: {
    title: string;
    text: string;
    url?: string;
  }): Promise<void> {
    await Share.share(data);
  }

  async copyToClipboard(text: string): Promise<void> {
    await Clipboard.write({ string: text });
  }

  async readFromClipboard(): Promise<string> {
    const result = await Clipboard.read();
    return result.value;
  }

  async openExternalUrl(url: string): Promise<void> {
    await Browser.open({ url, presentationStyle: "fullscreen" });
  }

  async takePhoto(options?: {
    quality?: number;
    allowEditing?: boolean;
    resultType?: CameraResultType;
    source?: CameraSource;
  }): Promise<string> {
    const result = await Camera.getPhoto({
      quality: options?.quality ?? 90,
      allowEditing: options?.allowEditing ?? true,
      resultType: options?.resultType ?? CameraResultType.DataUrl,
      source: options?.source ?? CameraSource.Camera,
    });
    return result.dataUrl || "";
  }

  async pickImages(options?: {
    quality?: number;
    limit?: number;
  }): Promise<string[]> {
    const result = await ImagePicker.pickImages({
      quality: options?.quality ?? 90,
      limit: options?.limit ?? 1,
    });
    return result.photos.map((p) => p.webPath || p.path || "");
  }

  async getCurrentPosition(): Promise<{ latitude: number; longitude: number }> {
    const position = await Geolocation.getCurrentPosition({
      enableHighAccuracy: true,
      timeout: 10000,
    });
    return {
      latitude: position.coords.latitude,
      longitude: position.coords.longitude,
    };
  }

  async watchPosition(
    callback: (position: { latitude: number; longitude: number }) => void,
  ): Promise<string> {
    const watchId = await Geolocation.watchPosition(
      {
        enableHighAccuracy: true,
        timeout: 10000,
      },
      (position, err) => {
        if (!err && position) {
          callback({
            latitude: position.coords.latitude,
            longitude: position.coords.longitude,
          });
        }
      },
    );
    return watchId;
  }

  async clearWatch(watchId: string): Promise<void> {
    await Geolocation.clearWatch({ id: watchId });
  }

  async getDeviceInfo(): Promise<any> {
    return Device.getInfo();
  }

  async getNetworkStatus(): Promise<{
    connected: boolean;
    connectionType: string;
  }> {
    return Network.getStatus();
  }

  async requestPermissions(): Promise<void> {
    await PushNotifications.requestPermissions();
    await LocalNotifications.requestPermissions();
    await Geolocation.requestPermissions();
  }

  async writeFile(path: string, data: string): Promise<void> {
    await Filesystem.writeFile({
      path,
      data,
      directory: Directory.Data,
      encoding: "utf8",
    });
  }

  async readFile(path: string): Promise<string> {
    const result = await Filesystem.readFile({
      path,
      directory: Directory.Data,
      encoding: "utf8",
    });
    return result.data as string;
  }

  async deleteFile(path: string): Promise<void> {
    await Filesystem.deleteFile({ path, directory: Directory.Data });
  }

  async listFiles(path: string): Promise<string[]> {
    const result = await Filesystem.readdir({
      path,
      directory: Directory.Data,
    });
    return result.files.map((f) => f.name);
  }

  async startSpeechRecognition(
    language: string = "en-US",
    onResult: (text: string, isFinal: boolean) => void,
  ): Promise<void> {
    await SpeechRecognition.start({
      language,
      popup: false,
      partialResults: true,
    });

    SpeechRecognition.addListener("result", (result) => {
      onResult(result.matches.join(" "), result.isFinal);
    });
  }

  async stopSpeechRecognition(): Promise<void> {
    await SpeechRecognition.stop();
  }

  async speak(text: string, lang: string = "en-US"): Promise<void> {
    await TextToSpeech.speak({
      text,
      lang,
      rate: 1.0,
      pitch: 1.0,
      volume: 1.0,
    });
  }

  async stopSpeaking(): Promise<void> {
    await TextToSpeech.stop();
  }

  async announceForAccessibility(message: string): Promise<void> {
    await ScreenReader.announce({ value: message });
  }

  isReady(): boolean {
    return this.initialized;
  }

  getPlatform(): string {
    return Capacitor.getPlatform();
  }

  isNative(): boolean {
    return Capacitor.isNativePlatform();
  }

  async cleanup(): Promise<void> {
    if (this.backgroundSyncInterval) {
      clearInterval(this.backgroundSyncInterval);
    }

    // Remove all listeners
    PushNotifications.removeAllListeners();
    LocalNotifications.removeAllListeners();
    BackgroundTask.removeAllListeners();
    Network.removeAllListeners();
    App.removeAllListeners();
    Keyboard.removeAllListeners();

    this.initialized = false;
  }
}

// Singleton instance
let nativeBridgeInstance: NativeBridge | null = null;

export function getNativeBridge(config?: NativeBridgeConfig): NativeBridge {
  if (!nativeBridgeInstance) {
    nativeBridgeInstance = new NativeBridge(config);
  }
  return nativeBridgeInstance;
}

export async function initializeNativeBridge(
  config?: NativeBridgeConfig,
): Promise<NativeBridge> {
  const bridge = getNativeBridge(config);
  await bridge.initialize();
  return bridge;
}

export default NativeBridge;
