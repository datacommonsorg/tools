/**
 * @fileoverview Hosts the upstream Data Commons Download tool via a same-origin iframe.
 */

import { UpstreamToolIframe } from "./iframe_upstream_tool";

/**
 * Embeds upstream Custom DC's Data Download Tool (Flask /tools/download).
 * All the iframe + chrome-hiding logic lives in UpstreamToolIframe; this
 * component just supplies the route and title.
 */
export function DataDownloadTool() {
  return (
    <UpstreamToolIframe src="/tools/download" title="Data Download Tool" />
  );
}
