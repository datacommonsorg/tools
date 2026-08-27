export interface CardSize {
  w: number;
  h: number;
}

export type CardVariant = 'text' | 'table' | 'chart';

/** Smallest size a card may be resized to. */
export const CARD_SIZE_MIN: CardSize = { w: 300, h: 220 } as const;

/**
 * Per-variant card footprint. `w` is the 'fixed' default width (unless user
 * resizes); `h` is the default *maximum* height — a card's actual height tracks
 * its rendered content (see `useCardAutoHeight`).
 */
export const CARD_VARIANT_SIZE_DEFAULT: Record<CardVariant, CardSize> = {
  text: { w: 650, h: 440 },
  table: { w: 650, h: 500 },
  chart: { w: 420, h: 720 },
} as const;
