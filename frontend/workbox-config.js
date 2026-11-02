/**
 * Workbox Configuration for VCOS
 * Generates service worker with precaching, routing, and background sync
 */

const { generateSW } = require('workbox-build');
const path = require('path');

const config = {
  // Source directory for build output
  globDirectory: path.join(__dirname, 'frontend', 'out'),
  
  // Patterns to include in precache manifest
  globPatterns: [
    '**/*.{js,css,html,png,svg,ico,woff,woff2,json,webmanifest}',
  ],
  
  // Ignore patterns
  globIgnores: [
    '**/node_modules/**/*',
    '**/*.map',
    '**/sw.js',
    '**/workbox-*.js',
  ],
  
  // Service worker output
  swDest: path.join(__dirname, 'frontend', 'public', 'sw.js'),
  
  // Runtime caching
  runtimeCaching: [
    {
      // Static assets - Cache First
      urlPattern: ({ request }) => 
        request.destination === 'style' || 
        request.destination === 'script' || 
        request.destination === 'font' ||
        request.destination === 'image',
      handler: 'CacheFirst',
      options: {
        cacheName: 'vcos-static-assets',
        expiration: {
          maxEntries: 100,
          maxAgeSeconds: 60 * 60 * 24 * 30, // 30 days
        },
        cacheableResponse: {
          statuses: [0, 200],
        },
      },
    },
    {
      // Pages and navigation - Stale While Revalidate
      urlPattern: ({ request }) => 
        request.mode === 'navigate' || request.destination === 'document',
      handler: 'StaleWhileRevalidate',
      options: {
        cacheName: 'vcos-pages',
        expiration: {
          maxEntries: 50,
          maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
        },
        cacheableResponse: {
          statuses: [0, 200],
        },
      },
    },
    {
      // API calls - Network First with Background Sync
      urlPattern: ({ url }) => url.pathname.startsWith('/api/'),
      handler: 'NetworkFirst',
      options: {
        cacheName: 'vcos-api',
        networkTimeoutSeconds: 10,
        plugins: [
          {
            cacheableResponse: { statuses: [0, 200] },
            expiration: {
              maxEntries: 200,
              maxAgeSeconds: 60 * 60 * 24, // 1 day
            },
            backgroundSync: {
              name: 'api-requests',
              options: {
                maxRetentionTime: 24 * 60, // 24 hours
              },
            },
          ],
      },
    },
    {
      // Static media - Cache First
      urlPattern: ({ url }) => 
        url.pathname.startsWith('/icons/') || 
        url.pathname.startsWith('/images/') || 
        url.pathname.startsWith('/fonts/'),
      handler: 'CacheFirst',
      options: {
        cacheName: 'vcos-media',
        plugins: [
          {
            cacheableResponse: { statuses: [0, 200] },
            expiration: {
              maxEntries: 50,
              maxAgeSeconds: 60 * 60 * 24 * 365, // 1 year
            },
          },
      },
    },
  ],
  
  // Navigation preload for faster page loads
  navigationPreload: true,
  
  // Cleanup outdated caches
  cleanupOutdatedCaches: true,
  
  // Skip waiting and claim clients immediately
  skipWaiting: true,
  clientsClaim: true,
  
  // Offline page fallback
  offlineGoogleAnalytics: false,
  
  // Custom service worker entry point
  swSrc: path.join(__dirname, 'frontend', 'public', 'sw-source.js'),
  
  // Manifest transforms
  manifestTransforms: [
    (manifestEntries) => {
      // Filter out unwanted entries
      const filtered = manifestEntries.filter(entry => 
        !entry.url.includes('node_modules') &&
        !entry.url.endsWith('.map') &&
        !entry.url.includes('sw.js') &&
        !entry.url.includes('workbox-')
      );
      return { manifest: filtered, warnings: [] };
    },
  ],
  
  // Don't precache these
  dontCacheBustURLsMatching: /\.\w{8}\./,
  
  // Maximum file size to precache (5MB)
  maximumFileSizeToCacheInBytes: 5 * 1024 * 1024,
};

// Generate service worker
async function generateServiceWorker() {
  try {
    const { count, size, warnings } = await generateSW(config);
    
    console.log(`Generated service worker with ${count} files (${(size / 1024).toFixed(2)} KB)`);
    
    if (warnings.length > 0) {
      console.warn('Warnings:', warnings);
    }
    
    return { count, size, warnings };
  } catch (error) {
    console.error('Failed to generate service worker:', error);
    throw error;
  }
}

module.exports = { generateServiceWorker, config };