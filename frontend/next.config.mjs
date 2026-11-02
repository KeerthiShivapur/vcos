/** @type {import('next').NextConfig} */
import withPWA from "next-pwa";

const withPWAConfig = withPWA({
  dest: "public",
  register: true,
  skipWaiting: true,
  disable: process.env.NODE_ENV === "development",
  runtimeCaching: [
    {
      urlPattern: /^https?.*/,
      handler: "NetworkFirst",
      options: {
        cacheName: "vcos-runtime",
        expiration: {
          maxEntries: 100,
          maxAgeSeconds: 24 * 60 * 60, // 24 hours
        },
        networkTimeoutSeconds: 10,
      },
    },
    {
      urlPattern: /\.(?:png|jpg|jpeg|svg|webp|gif|ico|woff|woff2)$/,
      handler: "CacheFirst",
      options: {
        cacheName: "vcos-static-assets",
        expiration: {
          maxEntries: 50,
          maxAgeSeconds: 30 * 24 * 60 * 60, // 30 days
        },
      },
    },
    {
      urlPattern:
        /\/api\/v1\/(company-experience|dashboard|meetings|projects|tasks|goals|people|decisions|collaboration|knowledge)/,
      handler: "NetworkFirst",
      options: {
        cacheName: "vcos-api",
        expiration: {
          maxEntries: 50,
          maxAgeSeconds: 5 * 60, // 5 minutes
        },
        networkTimeoutSeconds: 10,
      },
    },
    {
      urlPattern: /\/_next\/static\/.*/,
      handler: "CacheFirst",
      options: {
        cacheName: "vcos-next-static",
        expiration: {
          maxEntries: 100,
          maxAgeSeconds: 365 * 24 * 60 * 60, // 1 year
        },
      },
    },
  ],
  // Fallback for offline
  offlineGoogleAnalytics: true,
  manifest: {
    name: "VCOS - Virtual Company Operating System",
    short_name: "VCOS",
    description:
      "The operating system for virtual companies. One identity, one organization graph, one place to run your company.",
    start_url: "/",
    display: "standalone",
    background_color: "#f9fafb",
    theme_color: "#6366f1",
    orientation: "portrait-primary",
    scope: "/",
    icons: [
      {
        src: "/icon-72.png",
        sizes: "72x72",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/icon-96.png",
        sizes: "96x96",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/icon-128.png",
        sizes: "128x128",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/icon-144.png",
        sizes: "144x144",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/icon-152.png",
        sizes: "152x152",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/icon-192.png",
        sizes: "192x192",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/icon-384.png",
        sizes: "384x384",
        type: "image/png",
        purpose: "any maskable",
      },
      {
        src: "/icon-512.png",
        sizes: "512x512",
        type: "image/png",
        purpose: "any maskable",
      },
    ],
  },
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "public, max-age=0, must-revalidate" },
          { key: "Service-Worker-Allowed", value: "/" },
        ],
      },
      {
        source: "/manifest.json",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
      {
        source: "/icon-(.*)",
        headers: [
          {
            key: "Cache-Control",
            value: "public, max-age=31536000, immutable",
          },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/service-worker.js",
        destination: "/sw.js",
      },
    ];
  },
  // Transpile Capacitor plugins
  transpilePackages: [
    "@capacitor/app",
    "@capacitor/browser",
    "@capacitor/camera",
    "@capacitor/clipboard",
    "@capacitor/device",
    "@capacitor/filesystem",
    "@capacitor/geolocation",
    "@capacitor/haptics",
    "@capacitor/keyboard",
    "@capacitor/local-notifications",
    "@capacitor/network",
    "@capacitor/push-notifications",
    "@capacitor/splash-screen",
    "@capacitor/status-bar",
    "@capacitor/share",
    "@capacitor/toast",
    "@capacitor/background-task",
    "@capacitor/preferences",
    "@capacitor/camera",
    "@capacitor/image-picker",
    "@capacitor/media",
    "@capacitor/motion",
    "@capacitor/orientation",
    "@capacitor/screen-reader",
    "@capacitor/speech-recognition",
    "@capacitor/text-to-speech",
    "@capacitor/toast",
  ],
};

export default withPWAConfig(nextConfig);
