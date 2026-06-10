import { createContext, useContext, type ReactNode } from "react";
import { useBranding, DEFAULT_BRAND, type Branding } from "./useBranding";

const BrandingContext = createContext<Branding>(DEFAULT_BRAND);

export function BrandingProvider({ children }: { children: ReactNode }) {
  const { branding } = useBranding();
  return (
    <BrandingContext.Provider value={branding}>
      {children}
    </BrandingContext.Provider>
  );
}

export function useBrand(): Branding {
  return useContext(BrandingContext);
}
