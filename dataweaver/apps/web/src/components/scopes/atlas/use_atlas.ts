'use client';

import { createContext, useContext } from 'react';
import type { TLShapeId } from 'tldraw';
import type { AtlasContent, CardVariant } from './helpers';

/** The content shape that corresponds to a given card variant. */
type ContentForVariant<TVariant extends CardVariant> = Extract<
  AtlasContent,
  { variant: TVariant }
>;

/**
 * Handle returned by `atlas.add(...)`. Use it to populate a card with real
 * data as it arrives, or to remove the card from the canvas. The handle is
 * typed against the variant passed to `add`, so updates can only set fields
 * that belong to that variant.
 */
interface CardHandle<TVariant extends CardVariant> {
  readonly id: TLShapeId;
  readonly variant: TVariant;
  update(props: Partial<Omit<ContentForVariant<TVariant>, 'variant'>>): void;
  remove(): void;
}

/** Public atlas surface — what `useAtlas()` returns. */
export interface Atlas {
  add<TVariant extends CardVariant>(
    content: ContentForVariant<TVariant>,
  ): CardHandle<TVariant>;
}

/** @internal */
export const AtlasContext = createContext<Atlas | null>(null);

/** Read the atlas — must be used inside `<AtlasProvider>`. */
export const useAtlas = (): Atlas => {
  const context = useContext(AtlasContext);
  if (!context) {
    throw new Error("'useAtlas' must be used within 'AtlasProvider'.");
  }

  return context;
};
