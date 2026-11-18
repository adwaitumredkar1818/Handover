/**
 * Handover Motion System — Centralized Motion Configuration & Tokens
 *
 * Defines canonical animation durations, stagger intervals, and easings
 * across the entire landing page motion experience.
 */

export const MOTION_DURATIONS = {
  instant: 120,             // Micro-interactions, button active states
  fast: 220,                // Tooltip, tag hover, icon rotation (180-280ms band)
  standard: 420,            // Accordion, tab switch, panel updates (350-500ms band)
  medium: 450,              // Card lift, drawer slide-in, modal fade
  reveal: 600,              // Standard viewport reveal (450-750ms band)
  sectionReveal: 600,       // Backward-compatible alias for reveal
  sectionTransition: 750,   // Dark/light narrative transitions (600-900ms band)
  extended: 800,            // Knowledge transformation sequences
  graphDrawing: 1200,       // SVG relationship line path draw
  dossierAssembly: 1600,    // Complete handover dossier assembly sequence
} as const;

export const MOTION_STAGGERS = {
  small: 70,   // Stagger for 2-4 items (e.g. CTA buttons, assurance chips)
  medium: 90,  // Stagger for 5-8 items (e.g. 5 workflow steps, 8 domains)
  large: 110,  // Stagger for 9+ items (e.g. evidence table rows, footer columns)
} as const;

export const MOTION_EASINGS = {
  // Primary fluid easing for enterprise SaaS interfaces
  standard: "cubic-bezier(0.22, 1, 0.36, 1)",
  // Interactive state transitions (hover, focus, tab change)
  interactive: "cubic-bezier(0.4, 0, 0.2, 1)",
  // Entrances and reveals
  entrance: "cubic-bezier(0, 0, 0.2, 1)",
  // Physics-inspired gentle settle
  springGentle: "cubic-bezier(0.16, 1, 0.3, 1)",
  // Continuous linear motions (light beam, stream flow)
  linear: "linear",
} as const;

export type MotionDurationKey = keyof typeof MOTION_DURATIONS;
export type MotionStaggerKey = keyof typeof MOTION_STAGGERS;
export type MotionEasingKey = keyof typeof MOTION_EASINGS;
