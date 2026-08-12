/**
 * @fileoverview Tests for the useBranding hook's wire-format translation,
 * covering the `logo` key defined by branding.schema.json and the `logo_url`
 * legacy alias.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, afterEach, vi } from "vitest";
import { useBranding, DEFAULT_BRAND } from "./use_branding";

const BUCKET_URL = "https://storage.googleapis.com/example-config";

/** Stubs `/agent/brand` with a payload the hook's direct-branding path accepts. */
function mockBrandResponse(branding: Record<string, unknown>): void {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ brand_config_url: BUCKET_URL, branding }),
    }),
  );
}

describe("useBranding", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("resolves a relative `logo` path against the config bucket", async () => {
    mockBrandResponse({ instance_name: "Example", logo: "assets/logo.png" });

    const { result } = renderHook(() => useBranding());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.branding.logoUrl).toBe(`${BUCKET_URL}/assets/logo.png`);
    expect(result.current.branding.instanceName).toBe("Example");
  });

  it("accepts the legacy `logo_url` alias", async () => {
    mockBrandResponse({ logo_url: "assets/logo.png" });

    const { result } = renderHook(() => useBranding());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.branding.logoUrl).toBe(`${BUCKET_URL}/assets/logo.png`);
  });

  it("prefers `logo` when both keys are present", async () => {
    mockBrandResponse({ logo: "assets/new.png", logo_url: "assets/old.png" });

    const { result } = renderHook(() => useBranding());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.branding.logoUrl).toBe(`${BUCKET_URL}/assets/new.png`);
  });

  it("leaves an absolute logo URL untouched", async () => {
    mockBrandResponse({ logo: "https://cdn.example.com/logo.svg" });

    const { result } = renderHook(() => useBranding());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.branding.logoUrl).toBe("https://cdn.example.com/logo.svg");
  });

  it("fetches branding.json from the bucket when /agent/brand returns only the URL", async () => {
    // Public-bucket path: /agent/brand carries no `branding`, so the browser
    // fetches <bucket>/branding.json itself.
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ brand_config_url: BUCKET_URL }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ instance_name: "Public Example", logo: "assets/logo.png" }),
      });
    vi.stubGlobal("fetch", fetchMock);

    const { result } = renderHook(() => useBranding());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(fetchMock).toHaveBeenNthCalledWith(1, "/agent/brand", expect.anything());
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `${BUCKET_URL}/branding.json`,
      expect.anything(),
    );
    expect(result.current.branding.instanceName).toBe("Public Example");
    expect(result.current.branding.logoUrl).toBe(`${BUCKET_URL}/assets/logo.png`);
  });

  it("reports an error when the bucket's branding.json is unreachable", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ brand_config_url: BUCKET_URL }),
        })
        .mockResolvedValueOnce({ ok: false, status: 404 }),
    );

    const { result } = renderHook(() => useBranding());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.error).toContain("404");
    expect(result.current.branding.logoUrl).toBe(DEFAULT_BRAND.logoUrl);
  });

  it("falls back to the bundled defaults when /agent/brand fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 }));

    const { result } = renderHook(() => useBranding());

    await waitFor(() => expect(result.current.loaded).toBe(true));
    expect(result.current.branding.logoUrl).toBe(DEFAULT_BRAND.logoUrl);
  });
});
