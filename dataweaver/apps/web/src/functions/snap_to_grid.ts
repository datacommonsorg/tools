/**
 * Snap unit (page px at 1:1 zoom) cards drop onto after a drag or resize.
 * Matches the dot spacing in `grid.module.scss` so drops land on a visible dot.
 */
export const GRID_SIZE = 20 as const;

/** Round `value` to the nearest multiple of `gridSize`. */
export const snapToGrid = (
  value: number,
  gridSize: number = GRID_SIZE,
): number => Math.round(value / gridSize) * gridSize;
