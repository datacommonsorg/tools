import { describe, expect, it } from 'vitest';
import { GRID_SIZE, snapToGrid } from './snap_to_grid';

describe('snapToGrid', () => {
  it('snaps numbers to the default grid size (20)', () => {
    expect(snapToGrid(0)).toBe(0);
    expect(snapToGrid(9)).toBe(0);
    expect(snapToGrid(10)).toBe(20);
    expect(snapToGrid(19)).toBe(20);
    expect(snapToGrid(21)).toBe(20);
    expect(snapToGrid(35)).toBe(40);
  });

  it('snaps negative values correctly', () => {
    expect(snapToGrid(-9)).toBe(-0);
    expect(snapToGrid(-11)).toBe(-20);
    expect(snapToGrid(-35)).toBe(-40);
  });

  it('supports custom grid sizes', () => {
    expect(snapToGrid(14, 10)).toBe(10);
    expect(snapToGrid(16, 10)).toBe(20);
    expect(snapToGrid(48, 50)).toBe(50);
  });

  it('exports GRID_SIZE as 20', () => {
    expect(GRID_SIZE).toBe(20);
  });
});
