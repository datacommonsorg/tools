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

function readRoute(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.location.hash.replace(/^#\/?/, "");
}

export function useHashRoute(): [string] {
  const [route, setRoute] = useState<string>(readRoute);

  useEffect(() => {
    const onChange = () => setRoute(readRoute());
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  return [route];
}
