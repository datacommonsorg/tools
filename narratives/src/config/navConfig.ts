/**
 * Represents an item in the top navigation bar.
 */
export interface NavItem {
  /**
   * Route ID matching the hash route value in App.tsx.
   */
  id: string;

  /**
   * Human-readable label displayed in the UI. Consistently formatted in sentence case.
   */
  label: string;

  /**
   * Target URL or hash link.
   */
  href: string;
}

/**
 * Top navigation configuration representing all application tabs.
 * Ordered matching the Figma reference (AppbarDataAgent).
 */
export const NAV_CONFIG: NavItem[] = [
  { id: "agent", label: "Data agent", href: "#/agent" },
  { id: "metrics", label: "Key metrics dashboard", href: "#/metrics" },
  { id: "download", label: "Data download tool", href: "#/download" },
  { id: "statvar", label: "Statistical variable explorer", href: "#/statvar" },
];
