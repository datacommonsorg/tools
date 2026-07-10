/**
 * @fileoverview Imperatively mounts Data Commons web components to bypass React 19 custom-element property-setter issues.
 */

import { useEffect, useRef } from "react";

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
 * `apiroot` is set to window.location.origin per upstream homepage.html.
 * Custom Data Commons instances proxy the public Data Commons API under
 * their own origin, so the components fetch from the deployed instance's
 * own /api/* routes (which include the instance's custom variables).
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

/** API root the DC components fetch from — the page origin, per upstream homepage.html. */
export const API_ROOT =
  typeof window !== "undefined" ? window.location.origin : "";

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
