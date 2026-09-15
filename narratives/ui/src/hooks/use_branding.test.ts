/**
 * @fileoverview Tests for useBranding, focused on the pre-paint seeding path:
 * the first render must already carry the instance's branding, because a first
 * render of DEFAULT_BRAND is exactly the visible flip this seeding exists to
 * remove.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useBranding, DEFAULT_BRAND } from "./use_branding";

/** A branding.json as the agent serves it: snake_case, assets already rewritten. */
const BASE_DC = {
  schema_version: "1",
  instance_name: "Data Commons",
  logo: "/agent/brand/assets/dc-logo-1a2b3c4d.svg",
  favicon: "/agent/brand/assets/favicon-9f8e7d6c.png",
  logo_text: "Data Commons",
  headline: "Data agent explorer",
  tagline: "powered by Google's Data Commons",
  colors: { primary: "#0B57D0", accent: "#0B57D0" },
  navigation: [] as Array<{ label: string; href: string }>,
  footer: { text: "Base Data Commons — built on Custom Data Commons." },
  suggestions: ["How big is the financial sector in Vietnam"],
};

/** Renders the hook while recording the headline seen on every single render. */
function renderRecording() {
  const seen: Array<string | undefined> = [];
  const view = renderHook(() => {
    const result = useBranding();
    seen.push(result.branding.headline);
    return result;
  });
  return { ...view, seen };
}

describe("useBranding", () => {
  beforeEach(() => {
    document.head.innerHTML = '<link rel="icon" href="/dc-logo.svg" />';
    document.title = "Custom DC";
    document.documentElement.removeAttribute("style");
    delete window.__BRAND__;
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  describe("seeded from the pre-paint global", () => {
    beforeEach(() => {
      window.__BRAND__ = BASE_DC;
    });

    it("carries the instance branding on the very first render", () => {
      const { seen } = renderRecording();
      // The assertion that matters: no render ever showed the neutral default.
      expect(seen).toEqual(["Data agent explorer"]);
      expect(seen).not.toContain(DEFAULT_BRAND.headline);
    });

    it("reports loaded immediately, without a fetch", () => {
      const { result } = renderRecording();
      expect(result.current.loaded).toBe(true);
      expect(result.current.error).toBeNull();
      expect(fetch).not.toHaveBeenCalled();
    });

    it("seeds the fields that previously flipped after load", () => {
      const { result } = renderRecording();
      const b = result.current.branding;
      expect(b.logoText).toBe("Data Commons");
      expect(b.logoUrl).toBe(BASE_DC.logo);
      expect(b.tagline).toBe("powered by Google's Data Commons");
      expect(b.suggestions).toEqual(BASE_DC.suggestions);
      // An explicit [] must survive as [] — "no header menu", not "use the
      // shipped tabs". Falling back here is what made the nav row appear and
      // then vanish.
      expect(b.navigation).toEqual([]);
    });

    it("fills unset fields from DEFAULT_BRAND", () => {
      const { result } = renderRecording();
      expect(result.current.branding.radiusCard).toBe(DEFAULT_BRAND.radiusCard);
    });

    it("maps the nested footer block", () => {
      const { result } = renderRecording();
      expect(result.current.branding.footerText).toBe(
        "Base Data Commons — built on Custom Data Commons.",
      );
    });

    it("still accepts the legacy flat footer_text alias", () => {
      window.__BRAND__ = { footer_text: "legacy" };
      const { result } = renderRecording();
      expect(result.current.branding.footerText).toBe("legacy");
    });

    it("applies the tab title and favicon", async () => {
      renderRecording();
      await waitFor(() => expect(document.title).toBe("Data Commons"));
      expect(
        document.querySelector<HTMLLinkElement>('link[rel="icon"]')?.getAttribute("href"),
      ).toBe(BASE_DC.favicon);
    });

    it("re-asserts the CSS variables in case brand.css failed", () => {
      renderRecording();
      expect(document.documentElement.style.getPropertyValue("--brand-primary")).toBe("#0B57D0");
    });

    it("does not pin variables the instance left unset", () => {
      renderRecording();
      // Must fall through to brand.css / index.css, not be frozen inline.
      expect(document.documentElement.style.getPropertyValue("--brand-radius-card")).toBe("");
    });
  });

  describe("brand.js ran but no branding is configured", () => {
    it("uses the shipped defaults and skips the fetch", () => {
      window.__BRAND__ = null;
      const { result } = renderRecording();
      expect(result.current.branding).toEqual(DEFAULT_BRAND);
      expect(result.current.loaded).toBe(true);
      expect(fetch).not.toHaveBeenCalled();
      // Nothing pinned inline: index.css's own fallbacks must stand.
      expect(document.documentElement.style.getPropertyValue("--brand-primary")).toBe("");
    });
  });

  describe("brand.js did not run (stale index.html, 404, network failure)", () => {
    it("falls back to fetching /agent/brand", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => ({ instance: "base-dc", branding: BASE_DC }),
        }),
      );
      const { result } = renderRecording();
      expect(fetch).toHaveBeenCalledWith("/agent/brand", expect.anything());
      await waitFor(() => expect(result.current.branding.headline).toBe("Data agent explorer"));
      expect(result.current.loaded).toBe(true);
    });

    it("degrades to the shipped design when the fetch fails", async () => {
      vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
      vi.spyOn(console, "warn").mockImplementation(() => {});
      const { result } = renderRecording();
      await waitFor(() => expect(result.current.loaded).toBe(true));
      expect(result.current.error).toBe("offline");
      expect(result.current.branding).toEqual(DEFAULT_BRAND);
      // A failed refresh must not overwrite colours brand.css may have set.
      expect(document.documentElement.style.getPropertyValue("--brand-primary")).toBe("");
    });
  });
});
