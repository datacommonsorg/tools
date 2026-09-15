import { createShapeId, type Editor, type TLShapeId } from 'tldraw';
import { beforeEach, describe, expect, it } from 'vitest';
import { CARD_GRID } from './config';
import type { CardBounds, CardSize } from './helpers';
import { registerCardPlacement } from './register_card_placement';

const TABLE: CardSize = { w: 650, h: 500 };
const CHART: CardSize = { w: 420, h: 720 };

const LAPTOP_WIDTH = 1920;
const MOBILE_WIDTH = 400;
const { gutter: LAPTOP_GUTTER, columns: LAPTOP_COLUMNS } = CARD_GRID.laptop;

interface StubShape {
  id: TLShapeId;
  type: 'card';
  x: number;
  y: number;
  props: CardSize;
  meta?: { originId: TLShapeId };
}

/** Stands in for the unregister callback each side effect returns. */
const noop = () => undefined;

/**
 * The slice of the editor that placement reads. Shapes are published only
 * once the whole batch has been through `beforeCreate`, as tldraw does: a
 * card created in a multi-shape operation cannot see its siblings.
 */
const stubEditor = (screenWidth: number) => {
  const shapes: StubShape[] = [];
  const beforeCreate: ((shape: StubShape) => StubShape)[] = [];

  const editor = {
    getViewportScreenBounds: () => ({ width: screenWidth, height: 1080 }),
    getViewportPageBounds: () => ({ minX: 0, minY: 0, maxX: 1920, maxY: 1080 }),
    getCurrentPageShapes: () => shapes,
    getShape: (id: TLShapeId) => shapes.find((shape) => shape.id === id),
    isIn: () => false,
    createShapes: (batch: StubShape[]) => {
      const created = batch.map((shape) =>
        beforeCreate.reduce((next, handler) => handler(next), shape),
      );
      shapes.push(...created);
      return created;
    },
    sideEffects: {
      registerBeforeCreateHandler: (
        _type: string,
        handler: (shape: StubShape) => StubShape,
      ) => {
        beforeCreate.push(handler);
        return noop;
      },
      registerBeforeChangeHandler: () => noop,
      registerAfterChangeHandler: () => noop,
      registerAfterCreateHandler: () => noop,
      registerAfterDeleteHandler: () => noop,
    },
  };

  return {
    editor: editor as unknown as Editor,
    shapes,
    /** Publish a card to the store, as tldraw does once a create commits. */
    commit: (id: TLShapeId, bounds: CardBounds) => {
      shapes.push({
        id,
        type: 'card',
        x: bounds.x,
        y: bounds.y,
        props: { w: bounds.w, h: bounds.h },
      });
    },
    /**
     * Paste or duplicate a set of cards, the way tldraw does: one
     * `createShapes` call carrying every clone. Returns where they landed.
     */
    createClones: (sizes: CardSize[]): CardBounds[] => {
      const origin = createShapeId('origin');
      const batch = sizes.map((size, index) => ({
        id: createShapeId(`clone-${index}`),
        type: 'card' as const,
        x: 0,
        y: 0,
        props: size,
        meta: { originId: origin },
      }));

      return editor
        .createShapes(batch)
        .map((shape) => ({ x: shape.x, y: shape.y, ...shape.props }));
    },
  };
};

const overlaps = (a: CardBounds, b: CardBounds): boolean =>
  a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

describe('registerCardPlacement', () => {
  let canvas: ReturnType<typeof stubEditor>;

  beforeEach(() => {
    canvas = stubEditor(LAPTOP_WIDTH);
  });

  // Test: First card on an empty canvas.
  // Situation: No cards exist and no cursor has been established.
  // Expectation: The card roots one gutter inside the viewport's top-left.
  it('roots the grid at the viewport corner when the canvas is empty', () => {
    const placement = registerCardPlacement(canvas.editor);

    const position = placement.place(createShapeId('a'), TABLE, {
      kind: 'batch',
      widths: [TABLE.w],
    });

    expect(position).toEqual({ x: LAPTOP_GUTTER, y: LAPTOP_GUTTER });
  });

  // Test: A new row clears a card the user dragged below the grid.
  // Situation: The cursor is rooted on a card that was dragged far down, so
  //   the tracked row's own height says nothing about the canvas.
  // Expectation: The next batch lands below the lowest card, not beside it.
  it('starts a new row below the lowest card on the canvas', () => {
    const placement = registerCardPlacement(canvas.editor);

    canvas.commit(createShapeId('existing'), { x: 0, y: 0, ...TABLE });
    canvas.commit(createShapeId('dragged'), { x: 0, y: 4000, ...TABLE });

    const position = placement.place(createShapeId('new'), TABLE, {
      kind: 'batch',
      widths: [TABLE.w],
    });

    expect(position.y).toBe(4000 + TABLE.h + LAPTOP_GUTTER);
  });

  // Test: A paste wider than the grid wraps without overlapping itself.
  // Situation: Four cards arrive in one `createShapes` call, so none of them
  //   reaches the store before the next is placed — a multi-card paste.
  // Expectation: The card that wraps clears the row its siblings occupy.
  it('wraps a multi-card paste below its own first row', () => {
    registerCardPlacement(canvas.editor);

    canvas.commit(createShapeId('existing'), { x: 0, y: 0, ...TABLE });

    const placed = canvas.createClones(
      Array.from({ length: LAPTOP_COLUMNS + 1 }, () => TABLE),
    );

    const [rowStart, ...rest] = placed;
    const wrapped = rest[rest.length - 1];
    if (!rowStart || !wrapped) throw new Error('expected a wrapped card');

    for (const sibling of placed.slice(0, LAPTOP_COLUMNS)) {
      expect(overlaps(wrapped, sibling)).toBe(false);
    }
    expect(wrapped.y).toBe(rowStart.y + TABLE.h + LAPTOP_GUTTER);
  });

  // Test: Single-column duplicate of two cards.
  // Situation: Mobile grid, two clones created in one operation.
  // Expectation: The second clone stacks below the first rather than on it.
  it('stacks a single-column paste instead of overlapping it', () => {
    const mobile = stubEditor(MOBILE_WIDTH);
    registerCardPlacement(mobile.editor);

    mobile.commit(createShapeId('existing'), { x: 0, y: 0, ...TABLE });

    const [first, second] = mobile.createClones([TABLE, TABLE]);
    if (!first || !second) throw new Error('expected two clones');

    expect(overlaps(first, second)).toBe(false);
    expect(second.y).toBeGreaterThanOrEqual(first.y + TABLE.h);
  });

  // Test: A paste is centered on the canvas's content.
  // Situation: Two clones of different widths pasted under one existing card.
  //   The first clone is placed before its sibling exists, so the row can
  //   only be centered if the batch was read from the creation itself.
  // Expectation: The row's midpoint matches the content's midpoint.
  it('centers a pasted row on the existing content', () => {
    registerCardPlacement(canvas.editor);

    canvas.commit(createShapeId('existing'), { x: 0, y: 0, ...TABLE });
    const contentCenter = TABLE.w / 2;

    const placed = canvas.createClones([TABLE, CHART]);
    const rowLeft = Math.min(...placed.map((card) => card.x));
    const rowRight = Math.max(...placed.map((card) => card.x + card.w));

    expect((rowLeft + rowRight) / 2).toBeCloseTo(contentCenter);
  });

  // Test: One row per registration batch.
  // Situation: Two batches arrive back to back with room left in the first
  //   batch's row, as happens when two query results stream in together.
  // Expectation: The second batch opens its own row instead of filling the
  //   leftover slot.
  it('gives each batch its own row', () => {
    const placement = registerCardPlacement(canvas.editor);

    canvas.commit(createShapeId('existing'), { x: 0, y: 0, ...TABLE });

    const first = placement.place(createShapeId('batch-1-a'), TABLE, {
      kind: 'batch',
      widths: [TABLE.w, TABLE.w],
    });
    canvas.commit(createShapeId('batch-1-a'), { ...first, ...TABLE });

    const firstSecondCard = placement.place(
      createShapeId('batch-1-b'),
      TABLE,
      null,
    );
    canvas.commit(createShapeId('batch-1-b'), { ...firstSecondCard, ...TABLE });

    const second = placement.place(createShapeId('batch-2-a'), TABLE, {
      kind: 'batch',
      widths: [TABLE.w],
    });

    expect(firstSecondCard.y).toBe(first.y);
    expect(second.y).toBeGreaterThan(first.y);
  });

  // Test: A batch's row is centered on the canvas's content.
  // Situation: Mixed-width batch of three cards under a single existing card.
  // Expectation: The row's midpoint matches the content's midpoint.
  it('centers a batch row on the existing content', () => {
    const placement = registerCardPlacement(canvas.editor);

    canvas.commit(createShapeId('existing'), { x: 0, y: 0, ...TABLE });
    const contentCenter = TABLE.w / 2;

    const widths = [TABLE.w, TABLE.w, CHART.w];
    const sizes = [TABLE, TABLE, CHART];
    const placed = sizes.map((size, index) => {
      const position = placement.place(
        createShapeId(`card-${index}`),
        size,
        index === 0 ? { kind: 'batch', widths } : null,
      );
      canvas.commit(createShapeId(`card-${index}`), { ...position, ...size });
      return { ...position, ...size };
    });

    const rowLeft = Math.min(...placed.map((card) => card.x));
    const rowRight = Math.max(...placed.map((card) => card.x + card.w));

    expect((rowLeft + rowRight) / 2).toBeCloseTo(contentCenter);
  });

  // Test: Repeated single-card batches do not walk sideways.
  // Situation: Three one-card batches added in sequence.
  // Expectation: Every batch lands at the same x — a row width assumed rather
  //   than measured would bias each row and drag the next one further out.
  it('does not drift horizontally across successive batches', () => {
    const placement = registerCardPlacement(canvas.editor);

    canvas.commit(createShapeId('existing'), { x: 0, y: 0, ...TABLE });

    const xs = [0, 1, 2].map((index) => {
      const id = createShapeId(`solo-${index}`);
      const position = placement.place(id, TABLE, {
        kind: 'batch',
        widths: [TABLE.w],
      });
      canvas.commit(id, { ...position, ...TABLE });
      return position.x;
    });

    expect(new Set(xs).size).toBe(1);
    expect(xs[0]).toBe(0);
  });

  // Test: A stray card occupying the next slot.
  // Situation: A card sits exactly where the row's next slot would go.
  // Expectation: Placement drops to a new row rather than overlapping it.
  it('avoids a stray card blocking the next slot in the row', () => {
    const placement = registerCardPlacement(canvas.editor);

    const first = placement.place(createShapeId('first'), TABLE, null);
    canvas.commit(createShapeId('first'), { ...first, ...TABLE });

    const blockerBounds: CardBounds = {
      x: first.x + TABLE.w + LAPTOP_GUTTER,
      y: first.y,
      ...TABLE,
    };
    canvas.commit(createShapeId('blocker'), blockerBounds);

    const second = placement.place(createShapeId('second'), TABLE, null);

    expect(overlaps({ ...second, ...TABLE }, blockerBounds)).toBe(false);
    expect(second.y).toBeGreaterThan(first.y);
  });
});
