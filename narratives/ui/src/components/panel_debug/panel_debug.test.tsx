/**
 * Copyright 2026 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
 * implied. See the License for the specific language governing
 * permissions and limitations under the License.
 */

/**
 * @fileoverview Tests for the debug panel: the slide-over's opening,
 * dismissal, and focus, and the sections it lists from a turn's tool calls and
 * chart blocks.
 */

import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react';
import {
  afterAll,
  afterEach,
  beforeAll,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { DEBUG_PANEL_COPY } from '@/src/components/panel_debug/copy_debug';
import { DebugPanel } from '@/src/components/panel_debug/panel_debug';
import type { ChatTurn, ToolCallEvent } from '@/src/hooks/use_sse_chat';
import { parseServerDebugReport } from '@/src/types/debug_report';

const FETCH_CALL: ToolCallEvent = {
  name: 'fetch_observations',
  arguments: { variable_dcid: 'Count_Person', place_dcids: ['country/FRA'] },
  status: 'success',
};

/** Builds a finished turn with one fetch call and the given overrides. */
const buildFinishedTurn = (overrides: Partial<ChatTurn> = {}): ChatTurn => ({
  userMessage: 'What is the population of France?',
  status: 'done',
  toolCalls: [FETCH_CALL],
  thoughts: [],
  text: 'France has about 68 million people.',
  blocks: [
    { index: 0, type: 'text', markdown: 'France has about 68 million people.' },
  ],
  provenance: [],
  ...overrides,
});

/** Builds a fetch call whose table summary reports the facet that served it. */
const buildServedFetchCall = (facetId: string): ToolCallEvent => ({
  ...FETCH_CALL,
  result: JSON.stringify({ facet_id: facetId }),
});

/** Builds a metadata call describing one facet of a named variable. */
const buildDescribedFacetCall = (
  facetProperties: Record<string, string>,
): ToolCallEvent => ({
  name: 'get_variable_metadata',
  arguments: { variable_dcids: ['Count_Person'] },
  status: 'success',
  result: JSON.stringify({
    provenances: {
      describedProvenance: {
        properties: { isPartOf: 'Described Dataset', ...facetProperties },
      },
    },
    variables: {
      Count_Person: {
        name: 'Total population',
        facets: [{ id: '111', provenanceId: 'describedProvenance' }],
      },
    },
  }),
});

/** Builds a turn whose open dialog renders close, link, and toggle controls. */
const buildMultiControlTurn = (): ChatTurn =>
  buildFinishedTurn({
    toolCalls: [
      buildDescribedFacetCall({ url: 'https://example.org/data' }),
      buildServedFetchCall('111'),
    ],
  });

/** Returns the rendered inspect trigger button. */
const getInspectButton = (): HTMLElement =>
  screen.getByLabelText(DEBUG_PANEL_COPY.openButtonLabel);

/** Returns the open slide-over's close button. */
const getCloseButton = (): HTMLElement =>
  screen.getByLabelText(DEBUG_PANEL_COPY.closeButtonLabel);

/** Returns the Copy JSON button in the drawer header. */
const getCopyJsonButton = (): HTMLElement =>
  screen.getByRole('button', { name: DEBUG_PANEL_COPY.copyJsonButtonLabel });

/** Dispatches a cancelable Tab keydown on document and reports defaultPrevented. */
const pressTabKey = (shiftKey = false): boolean =>
  !fireEvent.keyDown(document, { key: 'Tab', shiftKey });

/** Renders the inspector for the turn and opens its slide-over. */
const openInspector = (turn: ChatTurn) => {
  render(<DebugPanel turn={turn} />);
  fireEvent.click(getInspectButton());
};

/** Returns the scrim behind the open slide-over. */
const getScrim = (): HTMLElement => {
  const scrim = document.querySelector<HTMLElement>('div[aria-hidden="true"]');
  if (!scrim) {
    throw new Error('The scrim is not rendered.');
  }
  return scrim;
};

let prefersReducedMotion = false;
const reducedMotionListeners = new Set<() => void>();

/** Updates the stubbed prefers-reduced-motion query and notifies subscribers. */
const setReducedMotionPreference = (shouldReduce: boolean): void => {
  prefersReducedMotion = shouldReduce;
  for (const listener of reducedMotionListeners) {
    listener();
  }
};

beforeAll(() => {
  vi.stubGlobal('matchMedia', (query: string) => ({
    get matches() {
      return query.includes('prefers-reduced-motion') && prefersReducedMotion;
    },
    media: query,
    addEventListener: (_type: string, listener: () => void) => {
      if (query.includes('prefers-reduced-motion')) {
        reducedMotionListeners.add(listener);
      }
    },
    removeEventListener: (_type: string, listener: () => void) => {
      reducedMotionListeners.delete(listener);
    },
  }));
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  if (prefersReducedMotion) {
    setReducedMotionPreference(false);
  }
});

afterAll(() => {
  reducedMotionListeners.clear();
  vi.unstubAllGlobals();
});

describe('DebugPanel', () => {
  it('renders the inspect button even for a turn without tool calls', () => {
    // Test: The inspector entry point for a turn that called no tools.
    // Situation: A finished turn whose tool call list is empty.
    // Expectation: The trigger button renders and opens the dialog on click.
    render(<DebugPanel turn={buildFinishedTurn({ toolCalls: [] })} />);

    const trigger = getInspectButton();
    expect(trigger).toBeDefined();

    fireEvent.click(trigger);
    expect(screen.getByRole('dialog')).toBeDefined();
  });

  it('opens the dialog from the inspect button', () => {
    // Test: Opening the slide-over.
    // Situation: The inspect button of a finished turn is clicked.
    // Expectation: The dialog renders and the button reports it expanded.
    openInspector(buildFinishedTurn());

    expect(screen.getByRole('dialog')).toBeDefined();
    expect(getInspectButton().getAttribute('aria-expanded')).toBe('true');
  });

  it('moves focus to the close button on open', () => {
    // Test: Focus placement when the slide-over opens.
    // Situation: The inspect button is clicked.
    // Expectation: The close button holds focus.
    openInspector(buildFinishedTurn());

    expect(document.activeElement).toBe(getCloseButton());
  });

  it('closes the dialog from the close button', async () => {
    // Test: Dismissal by the close button.
    // Situation: The open slide-over's close button is clicked.
    // Expectation: The dialog exits and unmounts.
    openInspector(buildFinishedTurn());
    fireEvent.click(getCloseButton());

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  it('closes the dialog from the scrim', async () => {
    // Test: Dismissal by the scrim.
    // Situation: The scrim behind the open slide-over is clicked.
    // Expectation: The dialog exits and unmounts.
    openInspector(buildFinishedTurn());
    fireEvent.click(getScrim());

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  it('closes the dialog on Escape', async () => {
    // Test: Dismissal by the keyboard.
    // Situation: Escape is pressed while the slide-over is open.
    // Expectation: The dialog exits and unmounts.
    openInspector(buildFinishedTurn());
    fireEvent.keyDown(document, { key: 'Escape' });

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).toBeNull();
    });
  });

  it('unmounts the dialog synchronously on close when reduced motion is preferred', () => {
    // Test: Reduced-motion dismissal.
    // Situation: prefers-reduced-motion matches and the close button is clicked.
    // Expectation: The dialog has no motion transform and unmounts immediately.
    setReducedMotionPreference(true);
    openInspector(buildFinishedTurn());
    expect(screen.getByRole('dialog').style.transform).toBe('');

    fireEvent.click(getCloseButton());

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.querySelector('div[aria-hidden="true"]')).toBeNull();
  });

  it('mounts no portal into document.body before the drawer is opened', () => {
    // Test: Lazy portal mounting.
    // Situation: A finished turn renders its inspect trigger without opening.
    // Expectation: Neither a dialog nor a backdrop scrim exists in document.body.
    render(<DebugPanel turn={buildFinishedTurn()} />);

    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.body.querySelector('div[aria-hidden="true"]')).toBeNull();
  });

  it('portals the scrim and dialog into document.body outside the turn container', () => {
    // Test: Portal target for escaping the turn stacking context.
    // Situation: DebugPanel renders inside a mount container and is opened.
    // Expectation: Both the scrim and dialog mount under document.body outside
    //   the turn container.
    const { container } = render(<DebugPanel turn={buildFinishedTurn()} />);
    fireEvent.click(getInspectButton());

    const dialog = screen.getByRole('dialog');
    const scrim = getScrim();
    expect(container.contains(dialog)).toBe(false);
    expect(container.contains(scrim)).toBe(false);
    expect(document.body.contains(dialog)).toBe(true);
    expect(document.body.contains(scrim)).toBe(true);
  });

  it('marks the trigger, scrim, and dialog with data-non-print', () => {
    // Test: Print and PDF exclusion attributes.
    // Situation: The slide-over is opened on a finished turn.
    // Expectation: Trigger, scrim, and dialog each carry data-non-print="true".
    openInspector(buildFinishedTurn());

    expect(getInspectButton().getAttribute('data-non-print')).toBe('true');
    expect(getScrim().getAttribute('data-non-print')).toBe('true');
    expect(screen.getByRole('dialog').getAttribute('data-non-print')).toBe(
      'true',
    );
  });

  it('renders a 44x44 red bug_report trigger with hover rotation classes', () => {
    // Test: Trigger button sizing, color, icon glyph, and hover rotation.
    // Situation: DebugPanel renders for a finished turn with tool calls.
    // Expectation: The 44x44 trigger uses text-error and group, and wraps a
    //   Material bug_report SVG with motion-safe 25-degree hover rotation.
    render(<DebugPanel turn={buildFinishedTurn()} />);

    const trigger = getInspectButton();
    expect([...trigger.classList]).toEqual(
      expect.arrayContaining(['w-11', 'h-11', 'group', 'text-error']),
    );
    expect(trigger.classList.contains('text-on-surface-variant')).toBe(false);

    const icon = trigger.querySelector('svg');
    expect(icon?.getAttribute('viewBox')).toBe('0 -960 960 960');
    expect(icon?.getAttribute('aria-hidden')).toBe('true');
    expect([...(icon?.classList ?? [])]).toEqual(
      expect.arrayContaining([
        'motion-safe:transition-transform',
        'motion-safe:duration-400',
        'motion-safe:group-hover:rotate-25',
      ]),
    );
  });

  it('renders a 44x44 close button with an aria-hidden glyph', () => {
    // Test: Close button touch target and decorative glyph semantics.
    // Situation: The slide-over is open.
    // Expectation: The close button is w-11 h-11 and hides its glyph from AT.
    openInspector(buildFinishedTurn());

    const closeButton = getCloseButton();
    expect([...closeButton.classList]).toEqual(
      expect.arrayContaining(['w-11', 'h-11']),
    );
    expect(closeButton.querySelector('span')?.getAttribute('aria-hidden')).toBe(
      'true',
    );
  });

  it('wraps Tab focus from the last focusable control to the first', () => {
    // Test: Forward focus wrap inside the open dialog.
    // Situation: Focus sits on the dialog's last button and Tab is pressed.
    // Expectation: Default tabbing is prevented and focus wraps to the Copy JSON
    //   button.
    openInspector(buildMultiControlTurn());
    fireEvent.click(screen.getByRole('tab', { name: /Trajectory/ }));
    screen
      .getByRole('button', { name: 'Show raw response (18 chars)' })
      .focus();

    expect(pressTabKey()).toBe(true);
    expect(document.activeElement).toBe(getCopyJsonButton());
  });

  it('wraps Shift+Tab focus from the first focusable control to the last', () => {
    // Test: Backward focus wrap inside the open dialog.
    // Situation: Focus sits on the Copy JSON button and Shift+Tab is pressed.
    // Expectation: Default tabbing is prevented and focus wraps to the last
    //   control in the dialog.
    openInspector(buildMultiControlTurn());
    fireEvent.click(screen.getByRole('tab', { name: /Trajectory/ }));
    getCopyJsonButton().focus();
    const lastControl = screen.getByRole('button', {
      name: 'Show raw response (18 chars)',
    });

    expect(pressTabKey(true)).toBe(true);
    expect(document.activeElement).toBe(lastControl);
  });

  it('skips controls inside a display-none ancestor when wrapping focus', () => {
    // Test: Ancestor visibility check in the dialog focus trap.
    // Situation: The last tool-call item has display: none on its list item
    //   ancestor while focus sits on the Copy JSON button and Shift+Tab runs.
    // Expectation: Focus wraps to the preceding visible button rather than the
    //   control inside the hidden list item.
    openInspector(buildMultiControlTurn());
    fireEvent.click(screen.getByRole('tab', { name: /Trajectory/ }));
    getCopyJsonButton().focus();
    const hiddenChildButton = screen.getByRole('button', {
      name: 'Show raw response (18 chars)',
    });
    const precedingVisibleButton = screen.getByRole('button', {
      name: 'Show raw response (238 chars)',
    });
    const parentItem = hiddenChildButton.closest('li');
    if (!parentItem) {
      throw new Error('Expected tool-call toggle to be inside a list item.');
    }
    parentItem.style.display = 'none';

    expect(pressTabKey(true)).toBe(true);
    expect(document.activeElement).toBe(precedingVisibleButton);
  });

  it('skips disabled controls with an explicit tabindex when wrapping focus', () => {
    // Test: Disabled-element exclusion on the [tabindex] selector branch.
    // Situation: The last button carries both tabIndex={0} and disabled while
    //   focus sits on the Copy JSON button and Shift+Tab runs.
    // Expectation: Focus wraps to the preceding enabled button rather than the
    //   disabled tabIndex={0} button.
    openInspector(buildMultiControlTurn());
    fireEvent.click(screen.getByRole('tab', { name: /Trajectory/ }));
    getCopyJsonButton().focus();
    const lastButton = screen.getByRole('button', {
      name: 'Show raw response (18 chars)',
    }) as HTMLButtonElement;
    const precedingEnabledButton = screen.getByRole('button', {
      name: 'Show raw response (238 chars)',
    });
    lastButton.tabIndex = 0;
    lastButton.disabled = true;

    expect(pressTabKey(true)).toBe(true);
    expect(document.activeElement).toBe(precedingEnabledButton);
  });

  it('returns Tab focus into the dialog when focus has moved outside', () => {
    // Test: Focus containment when activeElement leaves the dialog.
    // Situation: Focus sits on the trigger while the dialog is open and Tab runs.
    // Expectation: Focus moves to the first focusable control inside the dialog.
    openInspector(buildFinishedTurn());
    getInspectButton().focus();

    expect(pressTabKey()).toBe(true);
    expect(document.activeElement).toBe(getCopyJsonButton());
  });

  it('restores focus to a connected trigger button when the dialog closes', () => {
    // Test: Focus restoration on dismissal.
    // Situation: The open dialog is dismissed while its trigger stays mounted.
    // Expectation: Focus returns to the trigger button.
    openInspector(buildFinishedTurn());

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(document.activeElement).toBe(getInspectButton());
  });

  it('skips focus restoration when the trigger button is disconnected', () => {
    // Test: Liveness guard when restoring focus on dismissal.
    // Situation: The turn container is detached from document.body before
    //   Escape closes the portaled dialog.
    // Expectation: Dismissal checks isConnected and does not call focus() on
    //   the detached trigger button.
    const { container } = render(<DebugPanel turn={buildFinishedTurn()} />);
    const trigger = getInspectButton();
    fireEvent.click(trigger);
    const focusSpy = vi.spyOn(trigger, 'focus');
    container.remove();

    fireEvent.keyDown(document, { key: 'Escape' });

    expect(trigger.isConnected).toBe(false);
    expect(focusSpy).not.toHaveBeenCalled();
  });

  it('copies the JSON turn debug report to clipboard on button click', async () => {
    // Test: Copy JSON clipboard success.
    // Situation: The Copy JSON button is clicked in the open drawer.
    // Expectation: navigator.clipboard.writeText is called with formatted JSON,
    //   the button text switches to "Copied", and the live region announces it.
    setReducedMotionPreference(true);
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: writeTextSpy },
    });

    const turn = buildFinishedTurn();
    openInspector(turn);

    const copyButton = getCopyJsonButton();
    fireEvent.click(copyButton);

    expect(writeTextSpy).toHaveBeenCalledTimes(1);
    const copiedPayload = writeTextSpy.mock.calls[0][0];
    const parsedReport = JSON.parse(copiedPayload);
    expect(parsedReport.userMessage).toBe(turn.userMessage);
    expect(parsedReport.serverReport).toBeNull();

    await waitFor(() => {
      const liveRegion = document.querySelector('[aria-live="polite"]');
      expect(liveRegion).not.toBeNull();
      expect(liveRegion?.textContent).toBe('Copied');
    });
  });

  it('copies the JSON turn debug report including serverReport when present', async () => {
    // Test: Copy JSON clipboard includes lossless serverReport.
    // Situation: Turn carries a rawServerReport with custom payload.
    // Expectation: navigator.clipboard.writeText receives JSON with matching serverReport.
    setReducedMotionPreference(true);
    const writeTextSpy = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: writeTextSpy },
    });

    const rawReport = { turn_id: 't-99', custom_metric: 42 };
    const turn = buildFinishedTurn({ rawServerReport: rawReport });
    openInspector(turn);

    const copyButton = getCopyJsonButton();
    fireEvent.click(copyButton);

    expect(writeTextSpy).toHaveBeenCalledTimes(1);
    const copiedPayload = writeTextSpy.mock.calls[0][0];
    expect(JSON.parse(copiedPayload).serverReport).toEqual(rawReport);
    await waitFor(() => {
      expect(
        screen.getAllByText(DEBUG_PANEL_COPY.copiedStatus).length,
      ).toBeGreaterThan(0);
    });
  });

  it('handles clipboard write rejection gracefully with Copy failed status', async () => {
    // Test: Copy JSON clipboard rejection error handling.
    // Situation: navigator.clipboard.writeText rejects with an error.
    // Expectation: The button displays "Copy failed" and status is announced.
    setReducedMotionPreference(true);
    const writeTextSpy = vi
      .fn()
      .mockRejectedValue(new Error('Permission denied'));
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: { writeText: writeTextSpy },
    });

    openInspector(buildFinishedTurn());
    const copyButton = getCopyJsonButton();
    fireEvent.click(copyButton);

    await waitFor(() => {
      expect(screen.getAllByText('Copy failed').length).toBeGreaterThan(0);
    });
  });

  it('handles unavailable navigator.clipboard with Copy failed status', async () => {
    // Test: Copy JSON when clipboard API is unavailable.
    // Situation: navigator.clipboard is undefined.
    // Expectation: The button displays "Copy failed".
    vi.stubGlobal('navigator', {
      ...navigator,
      clipboard: undefined,
    });

    openInspector(buildFinishedTurn());
    const copyButton = getCopyJsonButton();
    fireEvent.click(copyButton);

    expect(screen.getAllByText('Copy failed').length).toBeGreaterThan(0);
  });

  it('renders Overview tab by default with paired tab and tabpanel attributes', () => {
    // Test: Default tab selection and ARIA pairing.
    // Situation: DebugPanel opens on a finished turn.
    // Expectation: The Overview tab is active and tabpanel id and aria-labelledby pair with it.
    openInspector(buildFinishedTurn());

    const overviewTab = screen.getByRole('tab', { name: 'Overview' });
    expect(overviewTab.getAttribute('aria-selected')).toBe('true');

    const panel = screen.getByRole('tabpanel');
    expect(panel.getAttribute('aria-labelledby')).toBe(
      overviewTab.getAttribute('id'),
    );
    expect(panel.getAttribute('id')).toBe(
      overviewTab.getAttribute('aria-controls'),
    );
    expect(panel.tabIndex).toBe(0);
  });

  it('switches tabs and updates tabpanel attributes on tab click', () => {
    // Test: Tab switching across all 9 tabs in DebugPanelBody.
    // Situation: The user clicks Data, Trajectory, Analysis, Synthesis, Response, Timing, Tokens, and Configuration.
    // Expectation: active tab updates, tabpanel id updates, and corresponding tab content renders.
    openInspector(
      buildFinishedTurn({
        clientTimings: {
          submittedAt: '2026-11-04T12:00:00.000Z',
          totalMs: 400,
        },
        serverReport:
          parseServerDebugReport({
            turn_id: 'turn-d4c-test',
            terminal_state: 'complete',
            duration_ms: 450,
            tokens: { total_token_count: 130 },
            tables: [
              {
                table_id: 't0_panel_test',
                used_in_answer: true,
                variable_dcid: 'Count_Person',
                variable_name: 'Total population',
                row_count: 1,
              },
            ],
            scripts: ['ranking'],
            synthesis_prompt: {
              text: 'Test synthesis prompt text',
              truncated: false,
              total_chars: 26,
            },
            build_sha: 'sha-test-build',
          }) ?? undefined,
      }),
    );

    const dataTab = screen.getByRole('tab', { name: /Data/ });
    fireEvent.click(dataTab);
    expect(dataTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(
      dataTab.getAttribute('id'),
    );
    expect(screen.getByText('t0_panel_test')).toBeDefined();

    const trajectoryTab = screen.getByRole('tab', { name: /Trajectory/ });
    fireEvent.click(trajectoryTab);
    expect(trajectoryTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(
      trajectoryTab.getAttribute('id'),
    );

    const analysisTab = screen.getByRole('tab', { name: /Analysis/ });
    fireEvent.click(analysisTab);
    expect(analysisTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(
      analysisTab.getAttribute('id'),
    );
    expect(screen.getByText('Analysis summary')).toBeDefined();

    const synthesisTab = screen.getByRole('tab', { name: /Synthesis/ });
    fireEvent.click(synthesisTab);
    expect(synthesisTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(
      synthesisTab.getAttribute('id'),
    );
    expect(screen.getByText('Test synthesis prompt text')).toBeDefined();

    const responseTab = screen.getByRole('tab', { name: /Response/ });
    fireEvent.click(responseTab);
    expect(responseTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(
      responseTab.getAttribute('id'),
    );

    const timingTab = screen.getByRole('tab', { name: /Timing/ });
    fireEvent.click(timingTab);
    expect(timingTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(
      timingTab.getAttribute('id'),
    );

    const tokensTab = screen.getByRole('tab', { name: /Tokens/ });
    fireEvent.click(tokensTab);
    expect(tokensTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(
      tokensTab.getAttribute('id'),
    );
    expect(screen.getByText('Token totals')).toBeDefined();

    const configTab = screen.getByRole('tab', { name: /Configuration/ });
    fireEvent.click(configTab);
    expect(configTab.getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tabpanel').getAttribute('aria-labelledby')).toBe(
      configTab.getAttribute('id'),
    );
    expect(screen.getByText('sha-test-build')).toBeDefined();
  });

  it('displays non-zero trajectory badge on an aborted turn when tool calls exist only on serverReport', () => {
    // Test: Trajectory badge on aborted turn.
    // Situation: turn.toolCalls is empty, but serverReport has 2 tool calls.
    // Expectation: Trajectory tab badge displays 2.
    const serverReport = parseServerDebugReport({
      turn_id: 'turn-aborted-badge',
      terminal_state: 'error',
      duration_ms: 200,
      tokens: { total_token_count: 10 },
      tool_calls: [
        { name: 'fetch_observations', arguments: {}, duration_ms: 50 },
        { name: 'run_script', arguments: {}, duration_ms: 40 },
      ],
    });

    openInspector(
      buildFinishedTurn({
        toolCalls: [],
        serverReport: serverReport ?? undefined,
      }),
    );

    const trajectoryTab = screen.getByRole('tab', { name: /Trajectory 2/ });
    expect(trajectoryTab).toBeDefined();
  });
});
