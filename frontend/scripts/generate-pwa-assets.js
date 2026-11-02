#!/usr/bin/env node

/**
 * PWA Asset Generator for VCOS
 * Generates all required icons and splash screens for PWA and native apps
 */

const fs = require('fs');
const path = require('path');
const { createCanvas } = require('canvas');

const SIZES = {
  // PWA icons
  icons: [
    72, 96, 128, 144, 152, 192, 384, 512
  ],
  // iOS splash screens
  iosSplash: [
    { width: 640, height: 1136 },  // iPhone 5/SE
    { width: 750, height: 1334 },  // iPhone 6/7/8
    { width: 828, height: 1792 },  // iPhone XR/11
    { width: 1125, height: 2436 }, // iPhone X/XS/11 Pro
    { width: 1242, height: 2208 }, // iPhone 6/7/8 Plus
    { width: 1242, height: 2688 }, // iPhone XS Max/11 Pro Max
    { width: 1536, height: 2048 }, // iPad
    { width: 1668, height: 2224 }, // iPad Pro 10.5"
    { width: 1668, height: 2388 }, // iPad Pro 11"
    { width: 2048, height: 2732 }, // iPad Pro 12.9"
  ],
  // Android splash screens
  androidSplash: [
    { density: 'ldpi', width: 200, height: 320 },
    { density: 'mdpi', width: 320, height: 480 },
    { density: 'hdpi', width: 480, height: 800 },
    { density: 'xhdpi', width: 720, height: 1280 },
    { density: 'xxhdpi', width: 960, height: 1600 },
    { density: 'xxxhdpi', width: 1280, height: 1920 },
  ]
};

const COLORS = {
  primary: '#6366f1',
  background: '#ffffff',
  text: '#1e293b',
};

async function generateIcon(size) {
  const canvas = createCanvas(size, size);
  const ctx = canvas.getContext('2d');
  
  // Background
  ctx.fillStyle = COLORS.background;
  ctx.fillRect(0, 0, size, size);
  
  // Rounded rectangle background
  const radius = size * 0.2;
  ctx.beginPath();
  ctx.roundRect(0, 0, size, size, radius);
  ctx.fillStyle = COLORS.primary;
  ctx.fill();
  
  // VCOS logo - simplified
  const centerX = size / 2;
  const centerY = size / 2;
  const logoSize = size * 0.5;
  
  // Draw VCOS logo (simplified)
  ctx.fillStyle = COLORS.background;
  ctx.font = `bold ${logoSize * 0.6}px -apple-system, BlinkMacSystemFont, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('VCOS', centerX, centerY);
  
  // Add small indicator dots
  ctx.fillStyle = 'rgba(255,255,255,0.6)';
  const dotSize = size * 0.04;
  const dotSpacing = size * 0.15;
  for (let i = 0; i < 3; i++) {
    ctx.beginPath();
    ctx.arc(centerX + (i - 1) * dotSpacing, centerY + logoSize * 0.4, dotSize, 0, Math.PI * 2);
    ctx.fill();
  }
  
  return canvas.toBuffer('image/png');
}

async function generateSplashScreen(width, height, isIOS = true) {
  const canvas = createCanvas(width, height);
  const ctx = canvas.getContext('2d');
  
  // Background
  ctx.fillStyle = COLORS.background;
  ctx.fillRect(0, 0, width, height);
  
  // Center logo
  const centerX = width / 2;
  const centerY = height / 2;
  const logoSize = Math.min(width, height) * 0.3;
  
  // Background circle
  ctx.beginPath();
  ctx.arc(centerX, centerY, logoSize * 0.8, 0, Math.PI * 2);
  ctx.fillStyle = COLORS.primary;
  ctx.fill();
  
  // VCOS text
  ctx.fillStyle = COLORS.background;
  ctx.font = `bold ${logoSize * 0.5}px -apple-system, BlinkMacSystemFont, sans-serif`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText('VCOS', centerX, centerY - logoSize * 0.1);
  
  // Subtitle
  ctx.font = `${logoSize * 0.12}px -apple-system, BlinkMacSystemFont, sans-serif`;
  ctx.fillStyle = 'rgba(255,255,255,0.8)';
  ctx.fillText('Virtual Company Operating System', centerX, centerY + logoSize * 0.3);
  
  // Loading indicator
  const dotCount = 3;
  const dotSize = logoSize * 0.05;
  const dotSpacing = logoSize * 0.15;
  for (let i = 0; i < dotCount; i++) {
    ctx.beginPath();
    ctx.arc(
      centerX + (i - 1) * dotSpacing,
      centerY + logoSize * 0.5,
      dotSize,
      0,
      Math.PI * 2
    );
    ctx.fillStyle = 'rgba(255,255,255,0.6)';
    ctx.fill();
  }
  
  return canvas.toBuffer('image/png');
}

async function main() {
  console.log('🎨 Generating PWA assets for VCOS...\n');
  
  const publicDir = path.join(__dirname, '..', 'public');
  const iconsDir = path.join(publicDir, 'icons');
  const splashDir = path.join(publicDir, 'splash');
  
  // Create directories
  [iconsDir, splashDir].forEach(dir => {
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }
  
  console.log('📱 Generating PWA icons...');
  for (const size of SIZES.icons) {
    const buffer = await generateIcon(size);
    const filename = `icon-${size}.png`;
    fs.writeFileSync(path.join(iconsDir, filename), buffer);
    fs.writeFileSync(path.join(publicDir, filename), buffer); // Also in root for manifest
    console.log(`  ✅ ${filename}`);
  }
  
  console.log('\n📱 Generating iOS splash screens...');
  for (const { width, height } of SIZES.iosSplash) {
    const buffer = await generateSplashScreen(width, height, true);
    const filename = `splash-${width}x${height}.png`;
    fs.writeFileSync(path.join(splashDir, filename), buffer);
    console.log(`  ✅ ${filename}`);
  }
  
  console.log('\n🤖 Generating Android splash screens...');
  for (const { density, width, height } of SIZES.androidSplash) {
    const buffer = await generateSplashScreen(width, height, false);
    const dir = path.join(splashDir, `android-${density}`);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    const filename = `splash.png`;
    fs.writeFileSync(path.join(dir, filename), buffer);
    console.log(`  ✅ ${density}/${filename}`);
  }
  
  // Generate maskable icon (512x512 with padding)
  console.log('\n🎭 Generating maskable icon...');
  const maskableCanvas = createCanvas(512, 512);
  const maskableCtx = maskableCanvas.getContext('2d');
  
  // Background with safe zone padding (40% = 204.8px each side)
  const safeZone = 512 * 0.4;
  maskableCtx.fillStyle = COLORS.primary;
  maskableCtx.fillRect(0, 0, 512, 512);
  
  // Draw logo in safe zone
  const safeCenter = 256;
  const safeSize = 512 - safeZone * 2;
  maskableCtx.fillStyle = COLORS.background;
  maskableCtx.font = `bold ${safeSize * 0.5}px -apple-system, BlinkMacSystemFont, sans-serif`;
  maskableCtx.textAlign = 'center';
  maskableCtx.textBaseline = 'middle';
  maskableCtx.fillText('VCOS', safeCenter, safeCenter);
  
  const maskableBuffer = maskableCanvas.toBuffer('image/png');
  fs.writeFileSync(path.join(iconsDir, 'icon-512-maskable.png'), maskableBuffer);
  console.log('  ✅ icon-512-maskable.png');
  
  // Generate Apple touch icon
  console.log('\n🍎 Generating Apple touch icon...');
  const appleIconBuffer = await generateIcon(180);
  fs.writeFileSync(path.join(publicDir, 'apple-touch-icon.png'), appleIconBuffer);
  console.log('  ✅ apple-touch-icon.png');
  
  // Generate favicon.ico (32x32)
  console.log('\n🌐 Generating favicon.ico...');
  const faviconCanvas = createCanvas(32, 32);
  const faviconCtx = faviconCanvas.getContext('2d');
  faviconCtx.fillStyle = COLORS.primary;
  faviconCtx.fillRect(0, 0, 32, 32);
  faviconCtx.fillStyle = COLORS.background;
  faviconCtx.font = 'bold 18px sans-serif';
  faviconCtx.textAlign = 'center';
  faviconCtx.textBaseline = 'middle';
  faviconCtx.fillText('V', 16, 21);
  fs.writeFileSync(path.join(publicDir, 'favicon.ico'), faviconCanvas.toBuffer('image/png'));
  console.log('  ✅ favicon.ico');
  
  console.log('\n✨ All PWA assets generated successfully!');
  console.log('\n📁 Output directories:');
  console.log(`  Icons: ${iconsDir}`);
  console.log(`  Splash: ${splashDir}`);
  console.log('\n📋 Next steps:');
  console.log('  1. Add icons to public/ folder');
  console.log('  2. Update manifest.json with correct paths');
  console.log('  3. Run: npx cap sync (for native)');
  console.log('  4. Test PWA with: npx serve out');
}

main().catch(console.error);