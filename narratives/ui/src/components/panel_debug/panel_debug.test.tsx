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
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { VARIABLE_NAME_SEPARATOR } from '@/src/components/panel_debug/copy_debug';
import {
  DebugPanel,
  isDebugPanelEnabled,
} from '@/src/components/panel_debug/panel_debug';
import type {
  ChartItem,
  ChatTurn,
  ToolCallEvent,
} from '@/src/hooks/use_sse_chat';

const FETCH_CALL: ToolCallEvent = {
  name: 'fetch_observations',
  arguments: { variable_dcid: 'Count_Person', place_dcids: ['country/FRA'] },
  status: 'success',
};

const LINE_CHART: ChartItem = {
  vizType: 'line',
  title: 'Population, France',
  variableDcids: ['Count_Person'],
  placeDcids: ['country/FRA'],
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

/** Builds a get_variable_metadata call describing two facets of one variable. */
const buildMetadataCall = (): ToolCallEvent => ({
  name: 'get_variable_metadata',
  arguments: { variable_dcids: ['Count_Person'] },
  status: 'success',
  result: JSON.stringify({
    provenances: {
      usedProvenance: { properties: { isPartOf: 'Used Dataset' } },
      unusedProvenance: { properties: { isPartOf: 'Unused Dataset' } },
    },
    variables: {
      Count_Person: {
        facets: [
          { id: '111', provenanceId: 'usedProvenance' },
          { id: '999', provenanceId: 'unusedProvenance' },
        ],
      },
    },
  }),
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
  screen.getByLabelText('Inspect data sources for this answer');

/** Returns the open slide-over's close button. */
const getCloseButton = (): HTMLElement =>
  screen.getByLabelText('Close provenance inspector');

/** Dispatches a cancelable Tab keydown on document and reports defaultPrevented. */
const pressTabKey = (shiftKey = false): boolean =>
  !fireEvent.keyDown(document, { key: 'Tab', shiftKey });

/** Renders the inspector for the turn and opens its slide-over. */
const openInspector = (turn: ChatTurn) => {
  render(<DebugPanel turn={turn} />);
  fireEvent.click(
    screen.getByLabelText('Inspect data sources for this answer'),
  );
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
  it('renders nothing for a turn without tool calls', () => {
    // Test: The inspector entry point for a turn that called no tools.
    // Situation: A finished turn whose tool call list is empty.
    // Expectation: The component renders no element at all.
    const { container } = render(
      <DebugPanel turn={buildFinishedTurn({ toolCalls: [] })} />,
    );

    expect(container.firstChild).toBeNull();
  });

  it('opens the dialog from the inspect button', () => {
    // Test: Opening the slide-over.
    // Situation: The inspect button of a finished turn is clicked.
    // Expectation: The dialog renders and the button reports it expanded.
    openInspector(buildFinishedTurn());

    expect(screen.getByRole('dialog')).toBeTruthy();
    expect(
      screen
        .getByLabelText('Inspect data sources for this answer')
        .getAttribute('aria-expanded'),
    ).toBe('true');
  });

  it('moves focus to the close button on open', () => {
    // Test: Focus placement when the slide-over opens.
    // Situation: The inspect button is clicked.
    // Expectation: The close button holds focus.
    openInspector(buildFinishedTurn());

    expect(document.activeElement).toBe(
      screen.getByLabelText('Close provenance inspector'),
    );
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
    // Expectation: Default tabbing is prevented and focus wraps to the close
    //   button.
    openInspector(buildMultiControlTurn());
    screen
      .getByRole('button', { name: 'Show raw response (18 chars)' })
      .focus();

    expect(pressTabKey()).toBe(true);
    expect(document.activeElement).toBe(getCloseButton());
  });

  it('wraps Shift+Tab focus from the first focusable control to the last', () => {
    // Test: Backward focus wrap inside the open dialog.
    // Situation: Focus sits on the close button and Shift+Tab is pressed.
    // Expectation: Default tabbing is prevented and focus wraps to the last
    //   control in the dialog.
    openInspector(buildMultiControlTurn());
    const lastControl = screen.getByRole('button', {
      name: 'Show raw response (18 chars)',
    });

    expect(pressTabKey(true)).toBe(true);
    expect(document.activeElement).toBe(lastControl);
  });

  it('skips controls inside a display-none ancestor when wrapping focus', () => {
    // Test: Ancestor visibility check in the dialog focus trap.
    // Situation: The last tool-call item has display: none on its list item
    //   ancestor while focus sits on the close button and Shift+Tab runs.
    // Expectation: Focus wraps to the preceding visible button rather than the
    //   control inside the hidden list item.
    openInspector(buildMultiControlTurn());
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
    //   focus sits on the close button and Shift+Tab runs.
    // Expectation: Focus wraps to the preceding enabled button rather than the
    //   disabled tabIndex={0} button.
    openInspector(buildMultiControlTurn());
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
    expect(document.activeElement).toBe(getCloseButton());
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

  it('lists only the facets that supplied data', () => {
    // Test: The provenance listing filter.
    // Situation: A metadata call describes two facets, and the fetch call was
    //   served by only one of them.
    // Expectation: The serving facet's dataset is listed and the other
    //   facet's dataset is not.
    openInspector(
      buildFinishedTurn({
        toolCalls: [buildMetadataCall(), buildServedFetchCall('111')],
      }),
    );

    expect(screen.getByText('Provenances used')).toBeTruthy();
    expect(screen.getByText('Used Dataset')).toBeTruthy();
    expect(screen.queryByText('Unused Dataset')).toBeNull();
  });

  it('names an undescribed facet with the fallback name', () => {
    // Test: The provenance listing for a facet no metadata call described.
    // Situation: The fetch call was served by a facet absent from every
    //   metadata result.
    // Expectation: The facet is listed under the fallback name with its id.
    openInspector(
      buildFinishedTurn({ toolCalls: [buildServedFetchCall('555')] }),
    );

    expect(screen.getByText('(unnamed source)')).toBeTruthy();
    expect(screen.getByText('555')).toBeTruthy();
  });

  it('marks a variable found only during search', () => {
    // Test: The variable listing for a variable with no fetched data.
    // Situation: A metadata call names a variable that no fetch call reads,
    //   and a fetch call reads another variable.
    // Expectation: Only the unfetched variable carries the search note.
    openInspector(
      buildFinishedTurn({
        toolCalls: [
          {
            name: 'get_variable_metadata',
            arguments: { variable_dcids: ['Median_Age_Person'] },
            status: 'success',
          },
          FETCH_CALL,
        ],
      }),
    );

    expect(screen.getByText('Median_Age_Person')).toBeTruthy();
    expect(screen.getAllByText('(resolved during search)')).toHaveLength(1);
  });

  it('lists the places with their count', () => {
    // Test: The places listing.
    // Situation: Two fetch calls read two different places.
    // Expectation: The heading counts two places and both are listed.
    openInspector(
      buildFinishedTurn({
        toolCalls: [
          FETCH_CALL,
          {
            ...FETCH_CALL,
            arguments: {
              variable_dcid: 'Count_Person',
              place_dcids: ['country/DEU'],
            },
          },
        ],
      }),
    );

    expect(screen.getByText('Places (2)')).toBeTruthy();
    expect(screen.getByText('country/FRA, country/DEU')).toBeTruthy();
  });

  it('hides a raw response until its toggle is clicked', () => {
    // Test: The raw response disclosure.
    // Situation: A tool call carries a raw response, and its toggle is
    //   clicked once.
    // Expectation: The response is absent before the click and present
    //   after it.
    openInspector(
      buildFinishedTurn({
        toolCalls: [{ ...FETCH_CALL, result: 'RAW-PAYLOAD' }],
      }),
    );

    expect(screen.queryByText('RAW-PAYLOAD')).toBeNull();
    fireEvent.click(screen.getByText('Show raw response (11 chars)'));
    expect(screen.getByText('RAW-PAYLOAD')).toBeTruthy();
  });

  it('labels the raw response toggle with its state and length', () => {
    // Test: The raw response toggle label.
    // Situation: A tool call carries an 11-character raw response, and its
    //   toggle is clicked once.
    // Expectation: The label reads "Show" before the click and "Hide" after
    //   it, with the character count in both.
    openInspector(
      buildFinishedTurn({
        toolCalls: [{ ...FETCH_CALL, result: 'RAW-PAYLOAD' }],
      }),
    );

    fireEvent.click(screen.getByText('Show raw response (11 chars)'));
    expect(screen.getByText('Hide raw response (11 chars)')).toBeTruthy();
  });

  it('updates aria-expanded on the 44px raw response toggle', () => {
    // Test: Accessibility state and touch target height on raw response toggle.
    // Situation: A tool call carries a raw response and its toggle is clicked.
    // Expectation: The button has min-h-11 and switches aria-expanded from
    //   "false" to "true".
    openInspector(
      buildFinishedTurn({
        toolCalls: [{ ...FETCH_CALL, result: 'RAW-PAYLOAD' }],
      }),
    );

    const toggle = screen.getByRole('button', {
      name: 'Show raw response (11 chars)',
    });
    expect(toggle.classList.contains('min-h-11')).toBe(true);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');

    fireEvent.click(toggle);

    expect(toggle.getAttribute('aria-expanded')).toBe('true');
  });

  it('keeps at most one raw response open', () => {
    // Test: The raw response disclosure across calls.
    // Situation: Two tool calls carry raw responses; the first call's toggle
    //   is clicked, then the second call's.
    // Expectation: Only the second call's response is shown.
    openInspector(
      buildFinishedTurn({
        toolCalls: [
          { ...FETCH_CALL, result: 'RAW-A' },
          { ...FETCH_CALL, result: 'RAW-B' },
        ],
      }),
    );

    const [firstToggle, secondToggle] = screen.getAllByText(
      'Show raw response (5 chars)',
    );
    fireEvent.click(firstToggle);
    fireEvent.click(secondToggle);
    expect(screen.queryByText('RAW-A')).toBeNull();
    expect(screen.getByText('RAW-B')).toBeTruthy();
  });

  it('shows a variable name after its DCID', () => {
    // Test: The variable listing for a named variable.
    // Situation: A metadata call names the variable that a fetch call reads.
    // Expectation: The name follows the DCID after the separator.
    openInspector(
      buildFinishedTurn({
        toolCalls: [buildDescribedFacetCall({}), buildServedFetchCall('111')],
      }),
    );

    expect(
      screen.getByText(`${VARIABLE_NAME_SEPARATOR}Total population`.trim()),
    ).toBeTruthy();
  });

  it('omits a facet detail without a value', () => {
    // Test: The facet detail line for a facet with no unit.
    // Situation: The serving facet's metadata reports no unit.
    // Expectation: The facet id detail renders and no unit detail does.
    openInspector(
      buildFinishedTurn({
        toolCalls: [buildDescribedFacetCall({}), buildServedFetchCall('111')],
      }),
    );

    expect(screen.getByText('111').parentElement?.textContent).toBe(
      'facet 111',
    );
    expect(screen.queryByText('unit')).toBeNull();
  });

  it('links a facet URL in a new tab', () => {
    // Test: The facet URL link.
    // Situation: The serving facet's provenance reports a URL.
    // Expectation: A link opens the URL in a new tab without a referrer and
    //   carries the full URL as its title.
    const url = 'https://example.org/dataset?code=POP&filter=FRA';
    openInspector(
      buildFinishedTurn({
        toolCalls: [
          buildDescribedFacetCall({ url }),
          buildServedFetchCall('111'),
        ],
      }),
    );

    const link = screen.getByRole('link', { name: url });
    expect(link.getAttribute('href')).toBe(url);
    expect(link.getAttribute('title')).toBe(url);
    expect(link.getAttribute('target')).toBe('_blank');
    expect(link.getAttribute('rel')).toBe('noopener noreferrer');
  });

  it('renders an unsafe facet URL as plain text without a link', () => {
    // Test: Provenance section defense against unsafe schemes in tool output.
    // Situation: A serving facet's metadata carries a javascript: URL.
    // Expectation: The URL text stays visible in a span and no anchor renders.
    const unsafeUrl = 'javascript:alert(1)';
    openInspector(
      buildFinishedTurn({
        toolCalls: [
          buildDescribedFacetCall({ url: unsafeUrl }),
          buildServedFetchCall('111'),
        ],
      }),
    );

    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText(unsafeUrl).tagName).toBe('SPAN');
  });

  it('applies font-mono classes to monospaced debug fields', () => {
    // Test: Standard monospace utility classes in the debug drawer.
    // Situation: The slide-over renders variables, facets, charts, and tool
    //   calls.
    // Expectation: Monospaced fields carry font-mono or font-mono! and zero
    //   elements carry custom font-mono-* variants.
    openInspector(
      buildFinishedTurn({
        toolCalls: [buildDescribedFacetCall({}), buildServedFetchCall('111')],
        blocks: [{ index: 0, type: 'chart', chart: LINE_CHART }],
      }),
    );

    expect(
      screen.getByText('Count_Person').classList.contains('font-mono'),
    ).toBe(true);
    expect(
      screen.getByText('fetch_observations').classList.contains('font-mono'),
    ).toBe(true);
    const pre = screen.getByRole('dialog').querySelector('pre');
    expect(pre?.classList.contains('font-mono!')).toBe(true);
    expect(document.querySelector('[class*="font-mono-"]')).toBeNull();
  });

  it('marks an errored tool call', () => {
    // Test: The tool call listing for a failed call.
    // Situation: A tool call finished with status "error".
    // Expectation: The call carries the error marker.
    openInspector(
      buildFinishedTurn({ toolCalls: [{ ...FETCH_CALL, status: 'error' }] }),
    );

    expect(screen.getByText('· error')).toBeTruthy();
  });

  it('lists the charts from the turn chart blocks', () => {
    // Test: The chart listing of a turn streamed as blocks.
    // Situation: A finished turn holding a text block and a chart block.
    // Expectation: The "Charts requested" section lists the chart block's
    //   title.
    openInspector(
      buildFinishedTurn({
        blocks: [
          {
            index: 0,
            type: 'text',
            markdown: 'France has about 68 million people.',
          },
          { index: 1, type: 'chart', chart: LINE_CHART },
        ],
      }),
    );

    expect(screen.getByText('Charts requested')).toBeTruthy();
    expect(screen.getByText('Population, France')).toBeTruthy();
  });

  it('omits the chart section for a turn without charts', () => {
    // Test: The chart listing of a turn that rendered no chart.
    // Situation: A finished turn whose only block is text.
    // Expectation: No "Charts requested" section renders, while the tool
    //   calls section still does.
    openInspector(
      buildFinishedTurn({
        blocks: [
          {
            index: 0,
            type: 'text',
            markdown: 'France has about 68 million people.',
          },
        ],
      }),
    );

    expect(screen.queryByText('Charts requested')).toBeNull();
    expect(screen.getByText('Tool calls (1)')).toBeTruthy();
  });
});

describe('isDebugPanelEnabled', () => {
  let originalUrl = '';

  beforeEach(() => {
    originalUrl = window.location.href;
  });

  afterEach(() => {
    window.history.replaceState(null, '', originalUrl);
  });

  it('is enabled by ?debug=provenance', () => {
    // Test: The debug flag with its enabling value.
    // Situation: The page URL carries ?debug=provenance.
    // Expectation: The panel is enabled.
    window.history.replaceState(null, '', '/?debug=provenance');

    expect(isDebugPanelEnabled()).toBe(true);
  });

  it('is disabled by any other debug value', () => {
    // Test: The debug flag with a value other than provenance.
    // Situation: The page URL carries ?debug=1.
    // Expectation: The panel is disabled.
    window.history.replaceState(null, '', '/?debug=1');

    expect(isDebugPanelEnabled()).toBe(false);
  });

  it('is disabled without the debug parameter', () => {
    // Test: The debug flag when absent.
    // Situation: The page URL carries no query string.
    // Expectation: The panel is disabled.
    window.history.replaceState(null, '', '/');

    expect(isDebugPanelEnabled()).toBe(false);
  });
});
