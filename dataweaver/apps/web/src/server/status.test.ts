import { describe, expect, it } from 'vitest';
import { STATUS, TOOL_LABELS } from '~/server/types';

describe('STATUS.usingTool', () => {
  // Test: Exports TOOL_LABELS mapping for Data Commons MCP tools.
  // Situation: Validating known tool keys in TOOL_LABELS.
  // Expectation: Contains expected friendly labels for all known tools.
  it('defines friendly labels in TOOL_LABELS', () => {
    expect(TOOL_LABELS.search_indicators).toBe('Searching variables');
    expect(TOOL_LABELS.get_observations).toBe('Retrieving observations');
  });
  // Test: Maps known Data Commons MCP tools to human-readable action strings.
  // Situation: Gemini calls an MCP tool that has a defined entry in TOOL_LABELS.
  // Expectation: Formats the status with the friendly label and ellipsis without counts.
  it('maps known MCP tools to friendly action strings', () => {
    expect(STATUS.usingTool('search_indicators')).toBe(
      'Searching variables...',
    );
    expect(STATUS.usingTool('search_child_indicators')).toBe(
      'Searching regional variables...',
    );
    expect(STATUS.usingTool('get_variable_metadata')).toBe(
      'Retrieving variable metadata...',
    );
    expect(STATUS.usingTool('get_observations')).toBe(
      'Retrieving observations...',
    );
    expect(STATUS.usingTool('get_child_observations')).toBe(
      'Retrieving regional observations...',
    );
    expect(STATUS.usingTool('get_multi_entity_observations')).toBe(
      'Retrieving comparative observations...',
    );
    expect(STATUS.usingTool('resolve_entities')).toBe('Resolving places...');
    expect(STATUS.usingTool('find_entities')).toBe('Finding places...');
    expect(STATUS.usingTool('get_place_metadata')).toBe(
      'Fetching place data...',
    );
  });

  // Test: Falls back to clean label when an unmapped tool name is encountered.
  // Situation: A tool is called that is not registered in TOOL_LABELS.
  // Expectation: Formats the status as "Using tool: <tool>..." without denominator/count.
  it('falls back to "Using tool: <tool>..." for unmapped tools', () => {
    expect(STATUS.usingTool('custom_new_tool')).toBe(
      'Using tool: custom_new_tool...',
    );
  });
});
