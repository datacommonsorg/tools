/**
 * @fileoverview Exposes the Branding React Context Provider and hook for accessing
 * dynamic theme config variables inside consumer components.
 */

import React, { createContext, useContext, type ReactNode } from "react";
import { useBranding, DEFAULT_BRAND, type Branding } from "./use_branding";

const BrandingContext = createContext<Branding>(DEFAULT_BRAND);

/**
 * Context provider component that wraps the React application shell and exposes
 * the active Custom Data Commons instance branding parameters (such as colors, fonts,
 * logos, names, and customized metrics dashboard options).
 *
 * This provider triggers the fetch of `branding.json` configurations at mount and registers
 * custom CSS variables onto the HTML document root to apply custom themes dynamically.
 *
 * @example
 * ```tsx
 * import { BrandingProvider } from './hooks/branding_context';
 * 
 * function AppContainer() {
 *   return (
 *     <BrandingProvider>
 *       <Header />
 *       <MainContent />
 *     </BrandingProvider>
 *   );
 * }
 * ```
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
 * React hook to retrieve the current Custom Data Commons instance branding configurations
 * from the surrounding `BrandingProvider` context.
 *
 * Used by UI components like headers, footers, and charts to dynamically style themselves
 * matching the brand config.
 *
 * @returns The active instance branding settings (e.g. `instanceName`, `logoUrl`, `accentColor`).
 *
 * @example
 * ```tsx
 * import { useBrand } from '../hooks/branding_context';
 * 
 * function Logo() {
 *   const { logoUrl, instanceName } = useBrand();
 *   return <img src={logoUrl} alt={instanceName} />;
 * }
 * ```
 */
export function useBrand(): Branding {
  return useContext(BrandingContext);
}
