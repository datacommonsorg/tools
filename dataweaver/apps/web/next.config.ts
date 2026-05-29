import { join } from 'node:path';
import type { NextConfig } from 'next';

const NEXT_CONFIG: NextConfig = {
  reactStrictMode: true,
  reactCompiler: true,
  devIndicators: false,

  // Transpile the workspace design-tokens package, which ships TypeScript
  // (`@package/tokens` -> dist/tokens.ts) rather than pre-built JS.
  transpilePackages: ['@package/tokens'],

  // Auto-inject the shared Sass includes (breakpoints, helpers, keyframes,
  // typography, z-indices) into every Sass entry module. Includes only
  // '@forwards' definitions, so this emits no CSS; it removes the need to
  // repeat `@use "~/styles/includes" as *;` at the top of each component file.
  // `loadPaths` lets Sass resolve `@use "@package/tokens/..."` from node_modules.
  sassOptions: {
    additionalData: '@use "~/styles/includes" as *;\n',
    loadPaths: [join(import.meta.dirname, 'node_modules')],
  },

  compiler: {
    removeConsole:
      // Only allow the following console calls in production
      process.env.NODE_ENV === 'production'
        ? { exclude: ['warn', 'error', 'info'] }
        : false,
  },

  images: {
    imageSizes: [384],
    deviceSizes: [768, 1280, 1600],
    qualities: [90],
    remotePatterns: [
      {
        protocol: 'https',
        hostname: 'fonts.googleapis.com',
        pathname: '/**',
      },
    ],
  },
};

export default NEXT_CONFIG;
