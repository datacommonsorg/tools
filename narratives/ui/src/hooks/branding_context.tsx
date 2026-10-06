/**
 * @fileoverview Provides a React context exposing per-instance branding to the component tree.
 */

import { createContext, type ReactNode, useContext } from 'react';
import { type Branding, DEFAULT_BRAND, useBranding } from './use_branding';

const BrandingContext = createContext<Branding>(DEFAULT_BRAND);

/**
 * Fetches the instance's branding once at mount (via useBranding) and shares
 * it with the whole component tree. Mount it once near the app root, above
 * anything that calls {@link useBrand}.
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
 * Returns the current instance branding (colors, logo, suggestions, …).
 * Reads {@link DEFAULT_BRAND} until the fetched branding resolves.
 */
export function useBrand(): Branding {
  return useContext(BrandingContext);
}
