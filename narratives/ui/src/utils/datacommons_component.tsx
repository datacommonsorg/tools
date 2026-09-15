/**
 * @fileoverview Imperatively mounts Data Commons web components to bypass React 19 custom-element property-setter issues.
 */

import { useEffect, useRef, type RefObject } from "react";

/**
 * <DataCommonsComponent> — render a Data Commons web component (`<datacommons-*>`).
 *
 * Why a ref-driven imperative mount instead of `dangerouslySetInnerHTML`:
 *
 * React 19's custom-element handler sets non-`apiroot` props as JS
 * properties on the element instance, e.g. `element.variables =
 * "Count_Person"`. Several DC components' property setters don't parse
 * string input — e.g. `<datacommons-line>`'s `variables` setter stores
 * the string as-is and then crashes inside render on
 * `this.variables.map(...)`. Upstream's `homepage.html` works around
 * this by composing the element from an HTML string + setAttribute()
 * (so the component sees attributes, not properties).
 *
 * Earlier we used the same `dangerouslySetInnerHTML` trick. But chat
 * re-renders the chart card on every SSE chunk, and React's
 * `dangerouslySetInnerHTML` diffs by string identity — every parent
 * re-render with the same attrs still passes a NEW string object,
 * causing React to wipe and re-inject the element. The DC component's
 * internal React tree was mid-commit when this happened and threw
 * "Target container is not a DOM element" (React error #200).
 *
 * The fix: write the HTML into the host div ONCE on mount, and on
 * subsequent renders only call setAttribute() for attrs that actually
 * changed. This matches how a hand-written `<datacommons-line>` would
 * behave in a static HTML page and gives the DC component a stable DOM
 * node for its lifetime.
 *
 * `apiroot` used to be window.location.origin: the instance proxied the Data
 * Commons API under its own origin via the services container's nginx. That
 * container is gone, so the components fetch from datacommons.org directly.
 * This is a base-Data-Commons-only deployment, so there are no instance
 * variables to lose by doing so; an instance that ingests its own data would
 * have to serve /api/* again and point this back at its own origin.
 */

/** The Data Commons web-component tag names the UI can render. */
export type DataCommonsComponentTagName =
  | "datacommons-line"
  | "datacommons-bar"
  | "datacommons-map"
  | "datacommons-pie"
  | "datacommons-gauge"
  | "datacommons-highlight"
  | "datacommons-ranking"
  | "datacommons-scatter"
  | "datacommons-slider";

/** Attribute bag for one <datacommons-*> element; values are stringified into HTML attributes. */
export type DataCommonsComponentAttributes = Record<
  string,
  string | number | boolean | undefined
>;

/**
 * API root the DC components fetch from. Public Data Commons, which serves
 * these endpoints with an open CORS policy and needs no API key from the
 * browser. See the fileoverview for why this is not the page origin.
 */
export const API_ROOT = "https://datacommons.org";

/** Renders a <datacommons-*> element via a one-time imperative mount (see fileoverview). */
export function DataCommonsComponent({
  tag,
  ...attrs
}: { tag: DataCommonsComponentTagName } & DataCommonsComponentAttributes) {
  const hostRef = useRef<HTMLDivElement>(null);
  // Track the last attribute snapshot so re-renders can diff and only
  // touch attributes that actually changed — `setAttribute` triggers DC's
  // attributeChangedCallback and re-fetches, so we want it called rarely.
  const lastAttrsRef = useRef<DataCommonsComponentAttributes | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    // First commit: create the element imperatively and set the initial
    // attribute set via setAttribute so it hits the attribute path (not
    // React's property-setter path). Avoids innerHTML parsing and its
    // attribute-escaping pitfalls entirely.
    if (!lastAttrsRef.current) {
      const el = document.createElement(tag);
      for (const [k, v] of Object.entries(attrs)) {
        if (v === undefined || v === null || v === false) continue;
        if (v === true) el.setAttribute(k, "");
        else el.setAttribute(k, String(v));
      }
      host.appendChild(el);
      lastAttrsRef.current = { ...attrs };
      return;
    }
    // Subsequent renders: diff against the previous attribute snapshot
    // and only setAttribute for keys that changed. Don't touch innerHTML.
    const el = host.firstElementChild as HTMLElement | null;
    if (!el) return;
    const prev = lastAttrsRef.current;
    const allKeys = new Set([...Object.keys(prev), ...Object.keys(attrs)]);
    for (const k of allKeys) {
      const a = attrs[k];
      const b = prev[k];
      if (a === b) continue;
      if (a === undefined || a === null || a === false) {
        el.removeAttribute(k);
      } else if (a === true) {
        el.setAttribute(k, "");
      } else {
        el.setAttribute(k, String(a));
      }
    }
    lastAttrsRef.current = { ...attrs };
    // attrs is intentionally diffed via the ref above rather than listed
    // as a dep — that would require deep-equality memoisation in every
    // caller, and getting it wrong replays the original bug.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  });

  return <div ref={hostRef} />;
}

/**
 * The message a DC component renders in place of a chart when its own fetch
 * came back with nothing to draw. `noDataErrorMessage` in the bundle's message
 * catalogue: an `<h4 class="text-danger">` above the header in the shared chart
 * container (line / bar / map / pie / scatter / gauge), and a bare element in
 * the ranking and highlight tiles. Matched without the trailing period so a
 * punctuation change upstream doesn't silently stop the check working.
 */
const NO_DATA_MESSAGE = "No data available";

/** How far the render of a mounted DC component has got. */
export type DcChartRenderState = "pending" | "empty" | "drawn";

/**
 * How long to keep watching a component before giving up on it settling.
 * Generous: the components fetch from datacommons.org, and a slow answer that
 * eventually draws must not be dropped for being slow.
 */
const SETTLE_BUDGET_MS = 20_000;

/** How often to re-read the component's shadow DOM while it is pending. */
const SETTLE_POLL_MS = 300;

/**
 * Reads whether a mounted `<datacommons-*>` element drew anything.
 *
 * Emptiness is not knowable at render time. Each component fetches its own
 * data from {@link API_ROOT} after mount, so a chart the agent configured
 * against variables it did hold observations for can still come back with
 * nothing for the place or date it was given — and then renders a card whose
 * only content is "No data available." over a grey placeholder. The only place
 * that outcome is visible is the component's own shadow DOM (open mode, so
 * readable), which is what this inspects.
 *
 * Deliberately fail-safe: every shape it does not recognise reads as
 * `pending`, so a change to the upstream bundle can only leave a card on
 * screen — never hide one that has data.
 */
export function dcChartRenderState(element: Element | null): DcChartRenderState {
  const root = (element as HTMLElement | null)?.shadowRoot;
  if (!root) return "pending"; // custom element has not upgraded yet
  const containers = root.querySelectorAll(".chart-container, .ranking-list");
  if (containers.length === 0) return "pending";
  for (const container of containers) {
    // Still fetching: the error node is not rendered yet, so its absence
    // says nothing.
    if (container.classList.contains("loading")) return "pending";
    if ((container.textContent ?? "").includes(NO_DATA_MESSAGE)) return "empty";
  }
  // A component that drew has marks: an <svg> for the plotted types, a table
  // for ranking, a formatted number for highlight. Until one of those exists
  // the component is still working, not empty.
  const drawn = root.querySelector("svg, .ranking-list table, .stat .number");
  return drawn ? "drawn" : "pending";
}

/**
 * Calls `onEmpty` once if the DC component under `hostRef` settles on having
 * no data to draw.
 *
 * Polls rather than observing: the state we need appears inside the
 * component's shadow root, which does not exist yet at mount (Lit attaches it
 * on first update) and which a MutationObserver on the host cannot see into.
 * The poll stops as soon as the component settles either way, and gives up
 * without reporting after {@link SETTLE_BUDGET_MS}.
 */
export function useDcChartEmptyNotice(
  hostRef: RefObject<HTMLElement | null>,
  tag: DataCommonsComponentTagName,
  onEmpty: () => void,
): void {
  // Held in a ref so an inline arrow from the caller does not restart the
  // poll on every parent re-render (chat re-renders on every SSE chunk).
  const onEmptyRef = useRef(onEmpty);
  onEmptyRef.current = onEmpty;

  useEffect(() => {
    const deadline = Date.now() + SETTLE_BUDGET_MS;
    const timer = window.setInterval(() => {
      const state = dcChartRenderState(
        hostRef.current?.querySelector(tag) ?? null,
      );
      if (state === "pending" && Date.now() < deadline) return;
      window.clearInterval(timer);
      if (state === "empty") onEmptyRef.current();
    }, SETTLE_POLL_MS);
    return () => window.clearInterval(timer);
  }, [hostRef, tag]);
}
