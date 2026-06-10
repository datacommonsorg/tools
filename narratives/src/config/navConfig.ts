export interface NavItem {
  // Route id — matches the hash route in App.tsx. Empty id is the default
  // (Agent) view.
  id: string;
  label: string;
  href: string;
}

// Nav matches Figma node 3427:16789 (`AppbarDataAgent`) of file
// kQtUhlVo9eCBoeqvdfAwpz — all four tabs in Figma order:
//   Data Agent → Key metrics dashboard → Data Download Tool → Statistical Variable Explorer
// April 30 ¶52 originally deferred Data Download Tool for MVP. Reinstated
// per later direction to keep the UI aligned with the Figma source.
// "Statistical Variable Explorer" replaces the April 30 transcript's
// auto-caption mis-hear "Start Work Explorer" — Figma is authoritative.
export const navConfig: NavItem[] = [
  { id: "agent", label: "Data Agent", href: "#/agent" },
  { id: "metrics", label: "Key metrics dashboard", href: "#/metrics" },
  { id: "download", label: "Data Download Tool", href: "#/download" },
  { id: "statvar", label: "Statistical Variable Explorer", href: "#/statvar" },
];
