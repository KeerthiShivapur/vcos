import { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.vcos.app",
  appName: "VCOS",
  webDir: "out",
  server: {
    androidScheme: "https",
    iosScheme: "https",
  },
  bundledWebRuntime: true,
  plugins: {
    SplashScreen: {
      launchShowDuration: 2000,
      backgroundColor: "#6366f1",
      showSpinner: false,
    },
    StatusBar: {
      style: "dark",
      backgroundColor: "#6366f1",
    },
    PushNotifications: {
      presentationOptions: ["badge", "sound", "alert"],
    },
    LocalNotifications: {
      smallIcon: "ic_stat_icon_config_sample",
      iconColor: "#6366f1",
    },
    BackgroundTask: {
      taskName: "vcos-background-sync",
    },
    App: {
      launchAutoHide: true,
    },
    Haptics: {},
    Keyboard: {
      resize: "body",
      style: "dark",
      resizeOnFullScreen: true,
    },
    Device: {},
    Network: {},
    Browser: {
      presentationStyle: "fullscreen",
    },
    Share: {},
    Clipboard: {},
    Filesystem: {},
    Geolocation: {},
    Camera: {},
    ImagePicker: {},
    Media: {},
    Motion: {},
    Orientation: {},
    ScreenReader: {},
    SpeechRecognition: {},
    TextToSpeech: {},
    Toast: {
      duration: "short",
      position: "bottom",
    },
  },
  ios: {
    contentInset: "automatic",
    scrollEnabled: true,
    limitsNavBarTextToLargeTitle: false,
    backgroundColor: "#ffffff",
    allowsLinkPreview: true,
    preferredContentMode: "mobile",
  },
  android: {
    allowMixedContent: true,
    captureInput: true,
    webContentsDebuggingEnabled: false,
    backgroundColor: "#ffffff",
    overrideUserAgent: "",
    appendUserAgent: "VCOS/1.0",
    allowFileAccessFromFileURLs: false,
    allowUniversalAccessFromFileURLs: false,
    enableZoom: false,
    forceFullScreen: false,
    userAgent: "",
  },
};

export default config;
