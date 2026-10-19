import { describe, expect, it } from 'vitest';
import { ImportError, importState, STATE_VERSION } from './serialization';

const buildFile = (payload: unknown): File =>
  new File([JSON.stringify(payload)], 'atlas-state.json', {
    type: 'application/json',
  });

describe('importState', () => {
  // Test: Exports from an older format are refused.
  // Situation: A v1 envelope, whose chart shape ids predate the variable suffix.
  // Expectation: A 'version-mismatch' ImportError, rather than importing cards
  // whose ids no longer match the ones the store computes.
  it('rejects an export from an earlier state version', async () => {
    const file = buildFile({
      version: 1,
      exportedAt: new Date().toISOString(),
      state: { nodes: {}, latestNodeId: null, cards: {} },
    });

    await expect(importState(file)).rejects.toMatchObject({
      name: 'ImportError',
      reason: 'version-mismatch',
    });
  });

  // Test: Current exports round-trip.
  // Situation: An envelope stamped with the current version.
  // Expectation: No error is thrown.
  it('accepts an export from the current state version', async () => {
    const file = buildFile({
      version: STATE_VERSION,
      exportedAt: new Date().toISOString(),
      state: { nodes: {}, latestNodeId: null, cards: {} },
    });

    await expect(importState(file)).resolves.toBeUndefined();
  });

  // Test: Payloads with no version are malformed, not mismatched.
  // Situation: JSON without a numeric `version` field.
  // Expectation: A 'malformed' ImportError.
  it('reports a missing version as malformed', async () => {
    const file = buildFile({ state: { nodes: {}, cards: {} } });

    await expect(importState(file)).rejects.toBeInstanceOf(ImportError);
    await expect(importState(file)).rejects.toMatchObject({
      reason: 'malformed',
    });
  });
});
