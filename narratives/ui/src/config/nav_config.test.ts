/**
 * @fileoverview Tests for branding-driven header navigation.
 *
 * The header tabs are one of the things an instance should be able to change
 * by editing branding.json rather than by editing this repo. The three cases
 * below are the ones whose failure is silent — a wrong answer here shows up as
 * missing or duplicated tabs, never as an error.
 */
import { describe, it, expect } from "vitest";
import { NAV_CONFIG, resolveNavItems } from "./nav_config";

describe("resolveNavItems", () => {
  it("falls back to the shipped tabs when branding says nothing about navigation", () => {
    // An instance with no branding.json, or one that omits `navigation`, must
    // keep the tabs this deployment ships with. Defaulting `navigation` in
    // DEFAULT_BRAND previously collapsed this case into the next one and
    // silently removed every tab.
    expect(resolveNavItems(undefined)).toEqual(NAV_CONFIG);
  });

  it("removes the header menu entirely for an explicit empty array", () => {
    // A public Data Commons instance ships without a header menu, so [] has to
    // mean "no tabs" rather than "no opinion". This is why the check is for
    // presence, not length.
    expect(resolveNavItems([])).toEqual([]);
  });

  it("replaces the shipped tabs with the instance's own", () => {
    const items = resolveNavItems([
      { label: "Explore", href: "#/agent" },
      { label: "Dashboards", href: "#/metrics" },
    ]);
    expect(items).toEqual([
      { id: "agent", label: "Explore", href: "#/agent" },
      { id: "metrics", label: "Dashboards", href: "#/metrics" },
    ]);
  });

  it("derives the route id from the href so the active tab still highlights", () => {
    // branding.json carries only label and href; the id used to match the
    // active hash route has to be recovered from the href.
    expect(resolveNavItems([{ label: "X", href: "#/statvar" }])[0].id).toBe("statvar");
    expect(resolveNavItems([{ label: "X", href: "#/metrics/extra" }])[0].id).toBe("metrics");
    expect(resolveNavItems([{ label: "X", href: "/" }])[0].id).toBe("");
  });
});
