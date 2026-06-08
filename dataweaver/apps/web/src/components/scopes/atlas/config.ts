import type { TLComponents } from 'tldraw';
import { Grid } from './components/grid';
import { InFrontOfTheCanvas } from './components/in_front_of_canvas';
import { ShapeCardUtil } from './shapes/card';
/**
 * Component overrides for tldraw - this allows us to inject our own React
 * components into the editor's UI via given 'slots'.
 */
export const ATLAS_COMPONENTS = {
  Grid,
  InFrontOfTheCanvas,
} as const satisfies TLComponents;

/** The shapes that the Atlas supports. */
export const ATLAS_SHAPES = [ShapeCardUtil] as const;

/** Atlas min zoom level. This is the minimum zoom enforced by tldraw. */
export const MIN_ZOOM = 0.25;

/** Atlas max zoom level. This is the maximum zoom enforced by tldraw. */
export const MAX_ZOOM = 3.25;

/** The range the actual zoom is rescaled onto for display in the controls. */
export const ZOOM_DISPLAY_RANGE = [0, 200] as const;

/**
 * How much the displayed zoom value changes per zoom in / out step. We divide
 * the display range evenly (i.e. here 200 / 20 = 10 steps).
 */
const ZOOM_DISPLAY_STEP = 20;

/**
 * The discrete zoom levels the controls step through, generated so they stay
 * evenly spaced across [MIN_ZOOM, MAX_ZOOM] — that even spacing is what makes
 * the displayed value increment by a constant `ZOOM_DISPLAY_STEP`.
 */
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
