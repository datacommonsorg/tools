import React, { createContext, useContext, type ReactNode } from "react";
import { useBranding, DEFAULT_BRAND, type Branding } from "./useBranding";

const BrandingContext = createContext<Branding>(DEFAULT_BRAND);

/**
 * Context provider wrapper that fetches and injects the active instance's branding definitions.
 */
export function BrandingProvider({ children }: { children: ReactNode }) {
  const { branding } = useBranding();
  return (
    <BrandingContext.Provider value={branding}>
      {children}
    </BrandingContext.Provider>
  );
}

/**
 * Hook to retrieve the current instance branding configurations (colors, font, logo, name).
 */
export function useBrand(): Branding {
  return useContext(BrandingContext);
}
