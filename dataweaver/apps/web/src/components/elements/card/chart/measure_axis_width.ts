const AXIS_FONT = '10px sans-serif';
const AXIS_PADDING = 12;
const MAX_AXIS_WIDTH = 150;
const DEFAULT_WIDTH = 40;

let cachedCanvas: HTMLCanvasElement | null = null;

function getContext(): CanvasRenderingContext2D | null {
  if (typeof document === 'undefined') return null;
  if (!cachedCanvas) cachedCanvas = document.createElement('canvas');
  return cachedCanvas.getContext('2d');
}

/**
 * Measures the pixel width needed to display the widest label in the list.
 * Returns a fixed value derived solely from the label content — never from
 * the chart/container width — so the result is stable during resizes.
 */
export function measureAxisWidth(labels: string[]): number {
  if (labels.length === 0) return DEFAULT_WIDTH;

  const ctx = getContext();
  if (!ctx) {
    const charWidth = labels.reduce((max, l) => Math.max(max, l.length * 6), 0);
    return Math.min(charWidth + AXIS_PADDING, MAX_AXIS_WIDTH);
  }

  ctx.font = AXIS_FONT;
  let maxWidth = 0;
  for (const label of labels) {
    const w = ctx.measureText(label).width;
    if (w > maxWidth) maxWidth = w;
  }
  return Math.min(maxWidth + AXIS_PADDING, MAX_AXIS_WIDTH);
}
