import type { CardType } from '~/server/types';

/**
 * Sentinel `placeDcid` for cards that render a node's cross-place comparison
 * rather than a single place's result.
 */
export const COMPARISON_PLACE_KEY = '__comparison';

/**
 * Shape-id segment for comparison cards. The sentinel already starts with the
 * `__` separator, so it is swapped for a bare segment to keep ids readable.
 */
const COMPARISON_SEGMENT = 'comparison';

interface CardShapeIdParts {
  historyNodeId: string;
  /** Place DCID the card targets, or `COMPARISON_PLACE_KEY`. */
  placeDcid: string;
  type: CardType;
  /** Set for chart cards that target one specific variable. */
  variableDcid?: string;
}

/**
 * Builds the canonical tldraw shape id for a card.
 *
 * The store keys cards by this id and relies on it to decide whether a card
 * already exists, so every producer must go through here — two call sites
 * formatting the id differently silently duplicate cards instead of focusing
 * the existing one.
 */
export const buildCardShapeId = ({
  historyNodeId,
  placeDcid,
  type,
  variableDcid,
}: CardShapeIdParts): string => {
  const placeSegment =
    placeDcid === COMPARISON_PLACE_KEY ? COMPARISON_SEGMENT : placeDcid;
  const variableSegment = variableDcid ? `__${variableDcid}` : '';
  return `shape:${historyNodeId}__${placeSegment}__${type}${variableSegment}`;
};
