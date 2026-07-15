/**
 * @fileoverview Lightweight hash-based router hook. We deliberately avoid
 * react-router-dom (the codebase intentionally has no router — see
 * implementation-reference.md §7.3). Hash navigation works without server-side
 * rewrites and survives reloads, while the nginx SPA fallback handles deep paths.
 */

import { useEffect, useState } from "react";

/**
 * Reads the current route token from the location hash.
 *
 * Empty hash (`""` / `"#"` / `"#/"`) resolves to `""` (the default / agent view).
 *
 * @warning `window.location.hash` is attacker-controllable input. The returned
 * token must never be fed unvalidated into redirects, `href`s, or other DOM
 * sinks. Any `?query` suffix is stripped so it cannot ride along into matching.
 * @returns The route token, e.g. `""` | `"metrics"` | `"download"` | `"statvar"`.
 */
function readRoute(): string {
  if (typeof window === "undefined") return "";
  return window.location.hash.replace(/^#\/?/, "").split("?")[0];
}

/**
 * Subscribes to hash changes and returns the current route token.
 *
 * @returns A single-element tuple holding the current route token.
 */
export function useHashRoute(): [string] {
  const [route, setRoute] = useState<string>(readRoute);

  useEffect(() => {
    const onChange = () => setRoute(readRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return [route];
}
