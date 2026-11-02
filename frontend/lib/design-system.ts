/**
 * VCOS Design System
 *
 * Comprehensive design system utilities and types for the VCOS application.
 */

import {
  designTokens,
  type DesignTokens,
  type ColorTokens,
  type TypographyTokens,
  type SpacingTokens,
} from "./design-tokens";

/* ============================================================================
   Color Utilities
   ============================================================================ */

export function getColorValue(
  color: { value: string },
  opacity?: number,
): string {
  if (opacity !== undefined && opacity < 1) {
    return `rgb(${color.value} / ${opacity})`;
  }
  return `rgb(${color.value})`;
}

export function getColorCSSVar(name: string, opacity?: number): string {
  const varName = `--${name}`;
  if (opacity !== undefined && opacity < 1) {
    return `rgb(var(${varName}) / ${opacity})`;
  }
  return `rgb(var(${varName}))`;
}

/* ============================================================================
   Spacing Utilities
   ============================================================================ */

export function getSpacing(value: keyof typeof designTokens.spacing): string {
  return designTokens.spacing[value];
}

export function getSpacingValue(value: number): string {
  return `${value * 4}px`;
}

/* ============================================================================
   Typography Utilities
   ============================================================================ */

export function getFontSize(
  size: keyof typeof designTokens.typography.fontSizes,
): string {
  return designTokens.typography.fontSizes[size];
}

export function getFontWeight(
  weight: keyof typeof designTokens.typography.fontWeights,
): string {
  return designTokens.typography.fontWeights[weight];
}

export function getLineHeight(
  height: keyof typeof designTokens.typography.lineHeights,
): string {
  return designTokens.typography.lineHeights[height];
}

export function getLetterSpacing(
  spacing: keyof typeof designTokens.typography.letterSpacings,
): string {
  return designTokens.typography.letterSpacings[spacing];
}

/* ============================================================================
   Shadow Utilities
   ============================================================================ */

export function getShadow(shadow: keyof typeof designTokens.shadows): string {
  return designTokens.shadows[shadow];
}

/* ============================================================================
   Transition Utilities
   ============================================================================ */

export function getTransition(
  duration: keyof typeof designTokens.transitions,
): string {
  return designTokens.transitions[duration];
}

/* ============================================================================
   Border Radius Utilities
   ============================================================================ */

export function getBorderRadius(
  radius: keyof typeof designTokens.borderRadius,
): string {
  return designTokens.borderRadius[radius];
}

/* ============================================================================
   Z-Index Utilities
   ============================================================================ */

export function getZIndex(zIndex: keyof typeof designTokens.zIndex): number {
  return designTokens.zIndex[zIndex];
}

/* ============================================================================
   Breakpoint Utilities
   ============================================================================ */

export function getBreakpoint(
  bp: keyof typeof designTokens.breakpoints,
): string {
  return designTokens.breakpoints[bp];
}

/* ============================================================================
   Color Utilities
   ============================================================================ */

export function hexToRgb(
  hex: string,
): { r: number; g: number; b: number } | null {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : null;
}

export function rgbToHex(r: number, g: number, b: number): string {
  return "#" + [r, g, b].map((x) => x.toString(16).padStart(2, "0")).join("");
}

export function rgbToHsl(
  r: number,
  g: number,
  b: number,
): { h: number; s: number; l: number } {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  let h = 0;
  let s = 0;
  const l = (max + min) / 2;

  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    switch (max) {
      case r:
        h = (g - b) / d + (g < b ? 6 : 0);
        break;
      case g:
        h = (b - r) / d + 2;
        break;
      case b:
        h = (r - g) / d + 4;
        break;
    }
    h /= 6;
  }
  return { h: h * 360, s: s * 100, l: l * 100 };
}

export function hslToRgb(
  h: number,
  s: number,
  l: number,
): { r: number; g: number; b: number } {
  h /= 360;
  s /= 100;
  l /= 100;

  const hue2rgb = (p: number, q: number, t: number) => {
    if (t < 0) t += 1;
    if (t > 1) t -= 1;
    if (t < 1 / 6) return p + (q - p) * 6 * t;
    if (t < 1 / 2) return q;
    if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
    return p;
  };

  if (l === 0) return { r: 0, g: 0, b: 0 };
  if (l === 1) return { r: 255, g: 255, b: 255 };

  let q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  let p = 2 * l - q;

  return {
    r: Math.round(hue2rgb(p, q, 240 / 360) * 255),
    g: Math.round(hue2rgb(p, q, 120 / 360) * 255),
    b: Math.round(hue2rgb(p, q, 0) * 255),
  };
}

function hue2rgb(p: number, q: number, t: number): number {
  if (t < 0) t += 1;
  if (t > 1) t -= 1;
  if (t < 1 / 6) return p + (q - p) * 6 * t;
  if (t < 1 / 2) return q;
  if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
  return p;
}

/* ============================================================================
   Contrast & Accessibility
   ============================================================================ */

export function getLuminance(r: number, g: number, b: number): number {
  const a = [r, g, b].map((v) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * a[0] + 0.7152 * a[1] + 0.0722 * a[2];
}

export function getContrastRatio(
  rgb1: { r: number; g: number; b: number },
  rgb2: { r: number; g: number; b: number },
): number {
  const l1 = getLuminance(rgb1.r, rgb1.g, rgb1.b);
  const l2 = getLuminance(rgb2.r, rgb2.g, rgb2.b);
  const lighter = Math.max(l1, l2);
  const darker = Math.min(l1, l2);
  return (lighter + 0.05) / (darker + 0.05);
}

export function meetsContrastRatio(
  ratio: number,
  level: "AA" | "AAA" = "AA",
  size: "normal" | "large" = "normal",
): boolean {
  const threshold =
    level === "AA" ? (size === "large" ? 3 : 4.5) : size === "large" ? 4.5 : 7;
  return ratio >= threshold;
}

export function getAccessibleTextColor(backgroundRgb: {
  r: number;
  g: number;
  b: number;
}): "light" | "dark" {
  const whiteContrast = getContrastRatio(
    { r: 255, g: 255, b: 255 },
    backgroundRgb,
  );
  const blackContrast = getContrastRatio({ r: 0, g: 0, b: 0 }, backgroundRgb);
  return whiteContrast > blackContrast ? "light" : "dark";
}

export function isMobile(width: number): boolean {
  return width < 768;
}

export function isTablet(width: number): boolean {
  return width >= 768 && width < 1024;
}

export function isDesktop(width: number): boolean {
  return width >= 1024;
}

/* ============================================================================
   Animation Utilities
   ============================================================================ */

export function getAnimationDuration(
  duration: keyof typeof designTokens.animation.duration,
): string {
  return designTokens.animation.duration[duration];
}

export function getEasing(
  easing: keyof typeof designTokens.animation.easing,
): string {
  return designTokens.animation.easing[easing];
}

/* ============================================================================
   Component Class Helpers
   ============================================================================ */

export function cn(
  ...classes: (string | undefined | null | false | Record<string, boolean>)[]
): string {
  return classes
    .filter((c): c is string | Record<string, boolean> => Boolean(c))
    .map((c) =>
      typeof c === "string"
        ? c
        : Object.entries(c)
            .filter(([, v]) => v)
            .map(([k]) => k)
            .join(" "),
    )
    .join(" ");
}

export function createComponentClasses(
  base: string,
  variants: Record<string, Record<string, string>>,
  selectedVariants: Record<string, string | undefined>,
  className?: string,
): string {
  let classes = base;

  for (const [variant, value] of Object.entries(selectedVariants)) {
    if (value && variants[variant]?.[value]) {
      classes += ` ${variants[variant][value]}`;
    }
  }

  if (className) {
    classes += ` ${className}`;
  }

  return classes;
}

/* ============================================================================
   Focus Ring Utilities
   ============================================================================ */

export function getFocusRing(
  color: "brand" | "danger" | "success" | "warning" = "brand",
  offset = 2,
): string {
  return `focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-${color} focus-visible:ring-offset-2 focus-visible:ring-offset-surface`;
}

/* ============================================================================
   Animation Helpers
   ============================================================================ */

export function createKeyframes(
  name: string,
  keyframes: Record<string, Record<string, string>>,
): string {
  const frames = Object.entries(keyframes)
    .map(
      ([key, value]) =>
        `${key} { ${Object.entries(value)
          .map(([k, v]) => `${k}: ${v};`)
          .join(" ")} }`,
    )
    .join(" ");
  return `@keyframes ${name} { ${frames} }`;
}

/* ============================================================================
   Gradient Utilities
   ============================================================================ */

export function createGradient(
  direction:
    "to-r" | "to-l" | "to-t" | "to-b" | "to-tr" | "to-tl" | "to-br" | "to-bl",
  stops: { color: string; position?: number }[],
): string {
  const stopsStr = stops
    .map(
      (stop) =>
        `${stop.color}${stop.position !== undefined ? ` ${stop.position}%` : ""}`,
    )
    .join(", ");
  return `linear-gradient(${direction}, ${stopsStr})`;
}

export const gradients = {
  brand:
    "linear-gradient(to right, rgb(var(--brand)), rgb(var(--brand-strong)))",
  brandVertical:
    "linear-gradient(to bottom, rgb(var(--brand)), rgb(var(--brand-strong)))",
  brandRadial:
    "radial-gradient(circle at center, rgb(var(--brand-soft)), transparent)",
  success: "linear-gradient(to right, rgb(var(--success)), rgb(52 211 153))",
  warning: "linear-gradient(to right, rgb(var(--warning)), rgb(251 191 36))",
  danger: "linear-gradient(to right, rgb(var(--danger)), rgb(248 113 113))",
  surface:
    "linear-gradient(to bottom, rgb(var(--surface)), rgb(var(--elevated)))",
  canvas: "linear-gradient(to bottom, rgb(var(--canvas)), rgb(var(--surface)))",
} as const;

/* ============================================================================
   Glass Morphism
   ============================================================================ */

export const glass = {
  light: "bg-surface/80 backdrop-blur-lg",
  medium: "bg-surface/90 backdrop-blur-xl",
  heavy: "bg-surface/95 backdrop-blur-2xl",
} as const;

/* ============================================================================
   Focus Ring
   ============================================================================ */

export const focusRing = {
  default:
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
  danger:
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-danger focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
  success:
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-success focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
  warning:
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-warning focus-visible:ring-offset-2 focus-visible:ring-offset-surface",
  inset:
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-surface focus-visible:ring-inset",
} as const;

/* ============================================================================
   Gradient Text
   ============================================================================ */

export const gradientText = {
  brand:
    "bg-gradient-to-r from-brand via-brand-strong to-brand bg-clip-text text-transparent",
  success:
    "bg-gradient-to-r from-success to-emerald-400 bg-clip-text text-transparent",
  warning:
    "bg-gradient-to-r from-warning to-amber-400 bg-clip-text text-transparent",
  danger:
    "bg-gradient-to-r from-danger to-red-400 bg-clip-text text-transparent",
} as const;

/* ============================================================================
   Export all
   ============================================================================ */

export const designSystem = {
  tokens: designTokens,
  colors: {
    get: getColorValue,
    cssVar: getColorCSSVar,
    hexToRgb,
    rgbToHex,
    rgbToHsl,
    hslToRgb,
    getLuminance,
    getContrastRatio,
    meetsContrastRatio,
    getAccessibleTextColor,
    gradients,
    glass,
  },
  typography: {
    getFontSize,
    getFontWeight,
    getLineHeight,
    getLetterSpacing,
  },
  spacing: {
    get: getSpacing,
    getValue: getSpacingValue,
  },
  shadows: {
    get: getShadow,
  },
  transitions: {
    get: getTransition,
  },
  borderRadius: {
    get: getBorderRadius,
  },
  animation: {
    durations: designTokens.animation.duration,
    easings: designTokens.animation.easing,
  },
  breakpoints: {
    get: getBreakpoint,
    isMobile,
    isTablet,
    isDesktop,
  },
  focusRing,
  gradientText,
  glass,
  gradients,
  cn,
  createComponentClasses,
  createKeyframes,
} as const;

export type DesignSystem = typeof designSystem;
