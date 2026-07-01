/**
 * @fileoverview Hook offering lightweight, client-side hash routing state management
 * which parses path segments and strips tracking query parameters.
 */

import { useEffect, useState } from "react";

/**
 * Normalizes and extracts the active route token from window.location.hash,
 * stripping leading hash symbols, slashes, and query parameters.
 */
function readRoute(): string {
  if (typeof window === "undefined") {
    return "";
  }
  const path = window.location.hash.replace(/^#\/?/, "");
  return path.split("?")[0];
}

/**
 * Lightweight hash-based router hook. We deliberately avoid react-router-dom
 * (the codebase intentionally has no router — see implementation-reference.md
 * §7.3). Hash navigation works without server-side rewrites and survives
 * reloads, while the nginx SPA fallback already handles deep paths.
 *
 * Subscribes to the window `hashchange` event and returns the active
 * normalized route segment as a single-item array tuple. An empty hash
 * (`""` / `"#"` / `"#/"`) resolves to `""` (treated as the default / agent
 * view).
 *
 * @example
 * ```tsx
 * const [route] = useHashRoute();   // "" | "metrics" | "explorer" | ...
 * <a href="#/metrics">Metrics</a>   // browsers handle the navigation
 * ```
 *
 * @returns The active route segment (untrusted user input from window.location).
 * @warning The returned string is user-controlled. Do not pass it directly to
 *          location redirects or anchor href attributes without validation.
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
