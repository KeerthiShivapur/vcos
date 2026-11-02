/**
 * VCOS Design Tokens
 *
 * Centralized design tokens for the VCOS design system.
 * These tokens define the visual language of the application.
 */

export const designTokens = {
  // Color palette
  colors: {
    // Base colors (light mode)
    light: {
      canvas: { value: "249 250 251", name: "Canvas background" },
      surface: { value: "255 255 255", name: "Surface background" },
      elevated: { value: "255 255 255", name: "Elevated surface" },
      line: { value: "226 232 240", name: "Border/line color" },
      ink: { value: "15 23 42", name: "Primary text color" },
      muted: { value: "100 116 139", name: "Muted text color" },
      faint: { value: "148 163 184", name: "Faint text color" },
      brand: {
        DEFAULT: { value: "79 70 229", name: "Brand primary" },
        strong: { value: "67 56 202", name: "Brand strong" },
        soft: { value: "238 242 255", name: "Brand soft background" },
      },
      success: { value: "5 150 105", name: "Success" },
      warning: { value: "217 119 6", name: "Warning" },
      danger: { value: "220 38 38", name: "Danger" },
    },
    // Dark mode colors
    dark: {
      canvas: { value: "8 10 16", name: "Canvas background" },
      surface: { value: "15 18 28", name: "Surface background" },
      elevated: { value: "20 24 36", name: "Elevated surface" },
      line: { value: "38 44 60", name: "Border/line color" },
      ink: { value: "226 232 240", name: "Primary text color" },
      muted: { value: "148 163 184", name: "Muted text color" },
      faint: { value: "100 116 134", name: "Faint text color" },
      brand: {
        DEFAULT: { value: "129 140 248", name: "Brand primary" },
        strong: { value: "165 180 252", name: "Brand strong" },
        soft: { value: "30 27 75", name: "Brand soft background" },
      },
      success: { value: "52 211 153", name: "Success" },
      warning: { value: "251 191 36", name: "Warning" },
      danger: { value: "248 113 113", name: "Danger" },
    },
  },

  // Typography
  typography: {
    fontFamilies: {
      sans: "var(--font-sans), system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      mono: "var(--font-mono), ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
    },
    fontSizes: {
      xs: "0.75rem", // 12px
      sm: "0.8125rem", // 13px
      base: "0.875rem", // 14px
      lg: "1rem", // 16px
      xl: "1.125rem", // 18px
      "2xl": "1.25rem", // 20px
      "3xl": "1.5rem", // 24px
      "4xl": "2rem", // 32px
      "5xl": "3rem", // 48px
    },
    fontWeights: {
      normal: "400",
      medium: "500",
      semibold: "600",
      bold: "700",
    },
    lineHeights: {
      tight: "1.25",
      normal: "1.5",
      relaxed: "1.75",
    },
    letterSpacings: {
      tight: "-0.02em",
      normal: "0",
      wide: "0.02em",
      wider: "0.05em",
    },
  },

  // Spacing
  spacing: {
    0: "0",
    1: "0.25rem", // 4px
    2: "0.5rem", // 8px
    3: "0.75rem", // 12px
    4: "1rem", // 16px
    5: "1.25rem", // 20px
    6: "1.5rem", // 24px
    8: "2rem", // 32px
    10: "2.5rem", // 40px
    12: "3rem", // 48px
    16: "4rem", // 64px
    20: "5rem", // 80px
    24: "6rem", // 96px
  },

  // Border radius
  borderRadius: {
    none: "0",
    sm: "4px",
    DEFAULT: "8px",
    md: "10px",
    lg: "12px",
    xl: "14px",
    "2xl": "16px",
    full: "9999px",
  },

  // Shadows
  shadows: {
    none: "none",
    sm: "0 1px 2px rgb(0 0 0 / 0.04)",
    DEFAULT: "0 1px 3px rgb(0 0 0 / 0.08)",
    md: "0 4px 6px -1px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.04)",
    lg: "0 10px 15px -3px rgb(0 0 0 / 0.08), 0 4px 6px -4px rgb(0 0 0 / 0.04)",
    xl: "0 20px 25px -5px rgb(0 0 0 / 0.08), 0 8px 10px -6px rgb(0 0 0 / 0.04)",
    "2xl": "0 25px 50px -12px rgb(0 0 0 / 0.2)",
    inner: "inset 0 2px 4px rgb(0 0 0 / 0.04)",
    popover: "0 12px 32px -8px rgb(0 0 0 / 0.18)",
    card: "0 1px 2px rgb(0 0 0 / 0.04)",
  },

  // Border width
  borderWidth: {
    0: "0",
    DEFAULT: "1px",
    2: "2px",
    4: "4px",
  },

  // Transitions
  transitions: {
    fast: "100ms ease",
    DEFAULT: "150ms ease",
    slow: "200ms ease",
    slower: "300ms ease",
  },

  // Z-index
  zIndex: {
    hide: -1,
    base: 0,
    dropdown: 100,
    sticky: 200,
    header: 40,
    modal: 500,
    popover: 600,
    tooltip: 700,
    toast: 800,
  },

  // Breakpoints
  breakpoints: {
    sm: "640px",
    md: "768px",
    lg: "1024px",
    xl: "1280px",
    "2xl": "1536px",
  },

  // Animation
  animation: {
    duration: {
      fast: "100ms",
      DEFAULT: "150ms",
      slow: "200ms",
      slower: "300ms",
    },
    easing: {
      linear: "linear",
      in: "ease-in",
      out: "ease-out",
      inOut: "ease-in-out",
    },
    keyframes: {
      fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
      fadeOut: { from: { opacity: "1" }, to: { opacity: "0" } },
      slideIn: {
        from: { transform: "translateY(-4px)", opacity: "0" },
        to: { transform: "translateY(0)", opacity: "1" },
      },
      slideOut: {
        from: { transform: "translateY(0)", opacity: "1" },
        to: { transform: "translateY(-4px)", opacity: "0" },
      },
      scaleIn: {
        from: { transform: "scale(0.95)", opacity: "0" },
        to: { transform: "scale(1)", opacity: "1" },
      },
      scaleOut: {
        from: { transform: "scale(1)", opacity: "1" },
        to: { transform: "scale(0.95)", opacity: "0" },
      },
    },
  },
} as const;

// Type exports
export type DesignTokens = typeof designTokens;
export type ColorTokens = typeof designTokens.colors.light;
export type TypographyTokens = typeof designTokens.typography;
export type SpacingTokens = typeof designTokens.spacing;
export type BorderRadiusTokens = typeof designTokens.borderRadius;
export type ShadowTokens = typeof designTokens.shadows;
export type TransitionTokens = typeof designTokens.transitions;

// Utility functions
export function getColorValue(
  color: { value: string },
  opacity?: number,
): string {
  if (opacity !== undefined && opacity < 1) {
    return `rgb(${color.value} / ${opacity})`;
  }
  return `rgb(${color.value})`;
}

export function getSpacing(value: keyof typeof designTokens.spacing): string {
  return designTokens.spacing[value];
}

export function getFontSize(
  size: keyof typeof designTokens.typography.fontSizes,
): string {
  return designTokens.typography.fontSizes[size];
}

export function getSpacingValue(value: number): string {
  return `${value * 4}px`;
}

export function getShadow(shadow: keyof typeof designTokens.shadows): string {
  return designTokens.shadows[shadow];
}

export function getTransition(
  duration: keyof typeof designTokens.transitions,
): string {
  return designTokens.transitions[duration];
}

// CSS variable names
export const cssVariables = {
  // Colors
  canvas: "--canvas",
  surface: "--surface",
  elevated: "--elevated",
  line: "--line",
  ink: "--ink",
  muted: "--muted",
  faint: "--faint",
  brand: "--brand",
  brandStrong: "--brand-strong",
  brandSoft: "--brand-soft",
  success: "--success",
  warning: "--warning",
  danger: "--danger",

  // Typography
  fontSans: "--font-sans",
  fontMono: "--font-mono",

  // Spacing (not used directly, but for reference)
  // Spacing is handled via Tailwind

  // Border radius
  radiusSm: "--radius-sm",
  radiusDefault: "--radius-default",
  radiusMd: "--radius-md",
  radiusLg: "--radius-lg",
  radiusXl: "--radius-xl",

  // Shadows
  shadowSm: "--shadow-sm",
  shadowDefault: "--shadow-default",
  shadowMd: "--shadow-md",
  shadowLg: "--shadow-lg",
  shadowXl: "--shadow-xl",
  shadow2xl: "--shadow-2xl",
  shadowInner: "--shadow-inner",
  shadowPopover: "--shadow-popover",
  shadowCard: "--shadow-card",

  // Transitions
  transitionFast: "--transition-fast",
  transitionDefault: "--transition-default",
  transitionSlow: "--transition-slow",
  transitionSlower: "--transition-slower",

  // Z-index
  zDropdown: "--z-dropdown",
  zSticky: "--z-sticky",
  zHeader: "--z-header",
  zModal: "--z-modal",
  zPopover: "--z-popover",
  zTooltip: "--z-tooltip",
  zToast: "--z-toast",

  // Breakpoints
  breakpointSm: "--breakpoint-sm",
  breakpointMd: "--breakpoint-md",
  breakpointLg: "--breakpoint-lg",
  breakpointXl: "--breakpoint-xl",
  breakpoint2xl: "--breakpoint-2xl",
} as const;

// Semantic color aliases for easier usage
export const semanticColors = {
  // Backgrounds
  background: {
    primary: "canvas",
    secondary: "surface",
    tertiary: "elevated",
  },
  // Text
  text: {
    primary: "ink",
    secondary: "muted",
    tertiary: "faint",
    inverse: "surface",
    brand: "brand",
    success: "success",
    warning: "warning",
    danger: "danger",
  },
  // Borders
  border: {
    default: "line",
    strong: "ink",
    focus: "brand",
    error: "danger",
    success: "success",
    warning: "warning",
  },
  // Interactive
  interactive: {
    primary: "brand",
    primaryHover: "brandStrong",
    secondary: "surface",
    secondaryHover: "line",
    danger: "danger",
    dangerHover: "danger/80",
  },
  // Status
  status: {
    success: "success",
    warning: "warning",
    danger: "danger",
    info: "brand",
  },
} as const;

export default designTokens;
