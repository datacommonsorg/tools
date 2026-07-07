import { EASE_OUT } from '@package/tokens/ts';
import { cubicBezier } from 'motion';
import type { TLCameraMoveOptions, TLComponents, TLUiOverrides } from 'tldraw';
import { ContextMenu } from './components/context_menu';
import { Grid } from './components/grid';
import { InFrontOfTheCanvas } from './components/in_front_of_canvas';
import type { CardSize, CardVariant } from './helpers';
import { AtlasSelectionForegroundOverlayUtil } from './overlays/selection_foreground';
import { ShapeCardUtil } from './shapes/card';
/**
 * Component overrides for tldraw - this allows us to inject our own React
 * components into the editor's UI via given 'slots'.
 */
export const ATLAS_COMPONENTS = {
  ContextMenu,
  Grid,
  InFrontOfTheCanvas,
} as const satisfies TLComponents;

/**
 * List of actions we don't want to support. These are included natively via
 * tldraw's actions registry so this deletes them so that they're not supported
 * both via the UI and keyboard shortcuts.
 */
const DISABLED_ACTION_IDS = [
  // Flatten (Shift+F) + Toggle-lock (Shift+L) — the only two with shortcuts
  'flatten-to-image',
  'toggle-lock',

  // Flip selection (Shift+H / Shift+V)
  'flip-horizontal',
  'flip-vertical',

  // Export as… (also lives in our own toolbar UI)
  'export-as-svg',
  'export-as-png',
  'download-original',

  // Copy as…
  'copy-as-svg',
  'copy-as-png',
  'copy-as-json',

  // Move to page (Atlas is single-page)
  'move-to-new-page',
] as const;

/**
 * List of tools we don't want to support.
 */
const DISABLED_TOOL_IDS = ['frame'] as const;

/** UI behaviour overrides for tldraw. */
export const ATLAS_OVERRIDES: TLUiOverrides = {
  actions(_editor, actions) {
    for (const id of DISABLED_ACTION_IDS) delete actions[id];
    return actions;
  },
  tools(_editor, tools) {
    for (const id of DISABLED_TOOL_IDS) delete tools[id];
    return tools;
  },
};

/** The shapes that Atlas supports. */
export const ATLAS_SHAPES = [ShapeCardUtil] as const;

/** Overlay utils for tldraw. */
export const ATLAS_OVERLAYS = [AtlasSelectionForegroundOverlayUtil] as const;

/** Atlas min zoom level. This is the minimum zoom enforced by tldraw. */
export const MIN_ZOOM = 0.25;

/** Atlas max zoom level. This is the maximum zoom enforced by tldraw. */
export const MAX_ZOOM = 3.25;

/**
 * The range the actual zoom is rescaled onto for display in the controls.
 * Anchored so tldraw's 1:1 zoom (level 1.0) reads as 100% at the midpoint.
 */
export const ZOOM_DISPLAY_RANGE = [0, 400] as const;

/**
 * How much the displayed zoom value changes per zoom in / out step. We divide
 * the display range evenly (i.e. here 400 / 25 = 16 steps).
 */
const ZOOM_DISPLAY_STEP = 25;

/** The number of discrete zoom steps between `MIN_ZOOM` and `MAX_ZOOM`. */
const ZOOM_STEP_COUNT =
  (ZOOM_DISPLAY_RANGE[1] - ZOOM_DISPLAY_RANGE[0]) / ZOOM_DISPLAY_STEP;

/**
 * The discrete zoom levels the controls step through, generated so they stay
 * evenly spaced across [MIN_ZOOM, MAX_ZOOM] — that even spacing is what makes
 * the displayed value increment by a constant `ZOOM_DISPLAY_STEP`.
 */
export const ZOOM_STEPS: readonly number[] = Array.from(
  { length: ZOOM_STEP_COUNT + 1 },
  (_, index) => MIN_ZOOM + (index * (MAX_ZOOM - MIN_ZOOM)) / ZOOM_STEP_COUNT,
);

/**
 * Per-variant card footprint. `w` is the fixed width; `h` is the *maximum*
 * height — a card's actual height tracks its rendered content (see
 * `useCardAutoHeight`) and is capped at this value - larger content scrolls.
 */
export const CARD_VARIANT_MAX: Record<CardVariant, CardSize> = {
  text: { w: 420, h: 440 },
  table: { w: 650, h: 500 },
  chart: { w: 420, h: 520 },
};

/** Minimum gap to keep between a placed card and any other card, in px. */
export const DISTANCE_FROM_OTHER_CARDS = 56;

/** Animation used when the camera pans to reveal a freshly placed card. */
export const KEEP_IN_VIEW_ANIMATION: TLCameraMoveOptions['animation'] = {
  duration: 500,
  easing: cubicBezier(...EASE_OUT),
} as const;
