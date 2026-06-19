import { useEffect, useState } from "react";

// Lightweight hash-based router. We deliberately avoid react-router-dom
// (the codebase intentionally has no router — see implementation-reference.md
// §7.3). Hash navigation works without server-side rewrites and survives
// reloads, while the nginx SPA fallback already handles deep paths.
//
// Usage:
//   const [route] = useHashRoute();          // "" | "metrics" | "explorer" | ...
//   <a href="#/metrics">Metrics</a>           // browsers handle the navigation
//
// Empty hash (`""` / `"#"` / `"#/"`) → "" (treat as default / agent).

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
 * Custom React hook that subscribes to window `hashchange` events and returns
 * the active normalized route segment as a single-item array tuple.
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
