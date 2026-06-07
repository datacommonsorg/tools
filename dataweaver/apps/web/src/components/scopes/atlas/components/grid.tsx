import type { TLGridProps } from 'tldraw';
import s from './grid.module.scss';

/**
 * Dot grid that tracks the camera. TLDraw transforms only its inner canvas
 * layer - so the grid is rendered through this slot (handed the live camera)
 * rather than as a static background on the outer container. Dots pan with the
 * camera ('x * z', 'y * z') but keep a fixed screen size (no zoom scaling).
 */
export const Grid = ({ x, y, z }: TLGridProps) => (
  <div
    className={s.grid}
    style={{ backgroundPosition: `${x * z}px ${y * z}px` }}
  />
);
