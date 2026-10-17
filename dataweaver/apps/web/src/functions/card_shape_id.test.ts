import { describe, expect, it } from 'vitest';
import { buildCardShapeId, COMPARISON_PLACE_KEY } from './card_shape_id';

describe('buildCardShapeId', () => {
  // Test: Chart cards are qualified by their variable.
  // Situation: A chart card for one place targeting a specific variable.
  // Expectation: The variable is appended so charts of different variables get distinct ids.
  it('appends the variable for variable-scoped chart cards', () => {
    expect(
      buildCardShapeId({
        historyNodeId: 'node_1',
        placeDcid: 'country/FRA',
        type: 'chart',
        variableDcid: 'UnemploymentRate',
      }),
    ).toBe('shape:node_1__country/FRA__chart__UnemploymentRate');
  });

  // Test: Cards without a variable.
  // Situation: A table card, which never targets a single variable.
  // Expectation: No trailing separator is emitted.
  it('omits the variable segment when no variable is given', () => {
    expect(
      buildCardShapeId({
        historyNodeId: 'node_1',
        placeDcid: 'country/FRA',
        type: 'table',
      }),
    ).toBe('shape:node_1__country/FRA__table');
  });

  // Test: The comparison sentinel is not emitted verbatim.
  // Situation: A comparison chart card, whose placeDcid is the '__comparison' sentinel.
  // Expectation: The sentinel collapses to a bare segment instead of doubling the separator.
  it('collapses the comparison sentinel into a single segment', () => {
    expect(
      buildCardShapeId({
        historyNodeId: 'node_1',
        placeDcid: COMPARISON_PLACE_KEY,
        type: 'chart',
        variableDcid: 'UnemploymentRate',
      }),
    ).toBe('shape:node_1__comparison__chart__UnemploymentRate');
  });
});
