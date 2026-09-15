/**
 * @fileoverview Tests for the useHashRoute hook.
 */

import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { useHashRoute } from "./use_hash_route";

describe("useHashRoute", () => {
  beforeEach(() => {
    window.location.hash = "";
  });

  it("should return empty string for default route", () => {
    const { result } = renderHook(() => useHashRoute());
    expect(result.current[0]).toBe("");
  });

  it("should parse standard routes", () => {
    const { result } = renderHook(() => useHashRoute());
    
    act(() => {
      window.location.hash = "#/metrics";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(result.current[0]).toBe("metrics");
  });

  it("should strip query parameters to avoid crashing", () => {
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      window.location.hash = "#/metrics?gclid=XYZ123&utm_source=test";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(result.current[0]).toBe("metrics");
  });

  it("should handle nested hash paths correctly", () => {
    const { result } = renderHook(() => useHashRoute());

    act(() => {
      window.location.hash = "#/explore/subpage";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });

    expect(result.current[0]).toBe("explore/subpage");
  });
});
