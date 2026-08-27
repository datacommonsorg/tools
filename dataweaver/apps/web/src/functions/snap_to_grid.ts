/**
 * Snap unit (page px at 1:1 zoom) cards drop onto after a drag or resize.
 * Matches the dot spacing in `grid.module.scss` so drops land on a visible dot.
 */
export const GRID_SIZE = 20 as const;

/**
 * Round `value` to the nearest multiple of `gridSize`.
 * If `gridSize <= 0`, snapping is bypassed and `value` is returned as-is.
 */
export const snapToGrid = (
  value: number,
  gridSize: number = GRID_SIZE,
): number => {
  if (gridSize <= 0) return value;
  return Math.round(value / gridSize) * gridSize;
};
