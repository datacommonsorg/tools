/**
 * @fileoverview Hosts the upstream Statistical Variable Explorer via a same-origin iframe.
 */

import { UpstreamToolIframe } from "./iframe_upstream_tool";

/**
 * Embeds upstream Custom DC's Statistical Variable Explorer (Flask
 * /tools/statvar). Mirrors DataDownloadTool — see UpstreamToolIframe for the
 * iframe + chrome-hiding implementation.
 *
 * One tool-specific override: upstream's `.dataset-selector-container` is a
 * flex-row with two <select>s that have `flex: 1 1 400px`. At the column
 * width we render at, the second select wraps to its own line — and that's
 * how upstream itself renders too. We force `flex-wrap: nowrap` so the two
 * dropdowns sit side-by-side (matches the design comp the team approved).
 */

const STATVAR_LAYOUT_CSS = `
  /* Keep label + both selects on a single row. */
  .dataset-selector-container {
    flex-wrap: nowrap !important;
    align-items: center !important;
    gap: 0.75rem !important;
  }
  .dataset-selector-container > .dataset-selector-label {
    flex: 0 0 auto !important;
  }
  .dataset-selector-container > select.dataset-selector-custom-input {
    flex: 1 1 0 !important;
    min-width: 0 !important;
    width: auto !important;
  }
`;

/** Statistical Variable Explorer tab — the upstream tool page embedded via iframe. */
export function StatVarExplorer() {
  return (
    <UpstreamToolIframe
      src="/tools/statvar"
      title="Statistical Variable Explorer"
      extraCss={STATVAR_LAYOUT_CSS}
    />
  );
}
