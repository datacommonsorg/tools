/**
 * @fileoverview Provides a same-origin iframe wrapper that embeds upstream Custom DC Flask tool pages.
 */

import { useCallback, useRef } from "react";

/**
 * Generic same-origin iframe wrapper for embedding upstream Custom DC
 * Flask-rendered tool pages (/tools/download, /tools/statvar, /tools/map, …)
 * directly inside our React app without showing upstream's own top nav.
 *
 * How it works:
 *   • iframe src is a relative path — same-origin in dev (Vite proxy →
 *     BACKEND_URL) and in prod (services-container nginx → Flask).
 *   • On the iframe's load event we inject a <style> into its contentDocument
 *     that hides upstream's nav/header/footer chrome, so the user sees ONE
 *     app bar (ours) and the bare tool body. Mirrors the IITM custom-dc-setup
 *     convention where the tool renders inside the host instance's frame,
 *     not the default Custom DC chrome.
 *
 * Same-origin requirement: contentDocument access requires the iframe URL
 * to be same-origin with the parent page. If a future deploy moves the tool
 * cross-origin, fall back to a server-side query-param flag (e.g.
 * /tools/download?embed=1) and a template branch that drops the nav.
 */

interface UpstreamToolIframeProps {
  src: string;
  title: string;
  // Optional tool-specific CSS appended after the generic chrome-hider rules.
  // Use for layout tweaks unique to one tool (e.g. StatVar's dropdown row).
  extraCss?: string;
}

/**
 * CSS targets are derived from probing the deployed upstream pages:
 *   • nav#main-navbar-container — 96px tall "Custom Data Commons / Tools / Docs"
 *   • header#main-header — wrapper around the nav
 *   • div#main — page body wrapper with padding-top:96px baked in to clear
 *     the (now-hidden) fixed nav
 */
const CHROME_HIDER_CSS = `
  #main-header,
  #main-navbar-container,
  nav.navbar,
  header.navbar,
  #main-footer,
  footer { display: none !important; }
  body { padding-top: 0 !important; margin-top: 0 !important; background: #fff !important; }
  #main { padding-top: 0 !important; margin-top: 0 !important; }
  html, body, .main-content, #main-pane { min-height: 0 !important; }
`;

const INJECTED_STYLE_ID = "cdc-iframe-chrome-hider";

/** Embeds an upstream Flask-rendered tool page in an iframe, hiding its own chrome. */
export function UpstreamToolIframe({
  src,
  title,
  extraCss,
}: UpstreamToolIframeProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);

  // Fires on every iframe `load` — including internal navigations within the
  // tool (the upstream React routers do client-side navigations, but the
  // top-level document doesn't reload, so this typically runs once). Guarded
  // with the style-id check so duplicate calls are harmless.
  const injectStyles = useCallback(() => {
    const doc = iframeRef.current?.contentDocument;
    if (!doc) return;
    if (doc.getElementById(INJECTED_STYLE_ID)) return;
    const style = doc.createElement("style");
    style.id = INJECTED_STYLE_ID;
    style.textContent = CHROME_HIDER_CSS + (extraCss ?? "");
    doc.head.appendChild(style);
  }, [extraCss]);

  return (
    <iframe
      ref={iframeRef}
      src={src}
      title={title}
      className="flex-1 w-full"
      style={{ border: "none", minHeight: 0 }}
      onLoad={injectStyles}
    />
  );
}
