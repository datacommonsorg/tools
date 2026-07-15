/// <reference types="vitest" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

// Dev-proxy defaults for a full local stack (Path B in ui/LOCAL_DEV.md).
const DEFAULT_BACKEND_URL = 'http://localhost:8080';
const DEFAULT_AGENT_URL = 'http://localhost:5001';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', '');
  const backendProxy = {
    target: env.BACKEND_URL || DEFAULT_BACKEND_URL,
    changeOrigin: true,
  };
  const agentProxy = {
    target: env.AGENT_URL || DEFAULT_AGENT_URL,
    changeOrigin: true,
  };
  return {
    // Vitest: happy-dom gives useHashRoute.test.ts a window/location + hashchange.
    test: {
      environment: 'happy-dom',
      globals: true,
    },
    plugins: [react(), tailwindcss()],
    // No GEMINI_API_KEY (or any secret) is injected into the client bundle.
    // All LLM calls go through the server-side agent proxy (/agent/*); the key
    // lives only in the agent container (Secret Manager). See dc-pr-standards §7.
    resolve: {
      alias: {
        '@': path.resolve(__dirname, '.'),
      },
    },
    server: {
      port: 3000,
      host: '0.0.0.0',
      // HMR is disabled in AI Studio via DISABLE_HMR env var.
      // Do not modify - file watching is disabled to prevent flickering during agent edits.
      hmr: process.env.DISABLE_HMR !== 'true',
      // Path A (UI + remote backend): set BACKEND_URL and AGENT_URL in .env.local.
      // Path B (full local stack):    leave them unset; defaults target localhost.
      // server.proxy is dev-only - `vite build` ignores it, so production is unaffected.
      proxy: {
        '/api':     backendProxy,
        '/mcp':     backendProxy,
        '/place':   backendProxy,
        '/browser': backendProxy,
        '/explore': backendProxy,
        '/core':    backendProxy,
        '/agent':   agentProxy,
        // /tools/* paths host upstream Flask-rendered pages we iframe — currently
        // /tools/download. /css, /custom_dc, /queryStore.js, /base.js, /download.js
        // and friends are the absolute-path assets those pages reference. All
        // routed to BACKEND_URL so the iframe behaves identically in dev and in
        // the baked production image (where nginx covers the same paths).
        '/tools':         backendProxy,
        '/css':           backendProxy,
        '/custom_dc':     backendProxy,
        '/queryStore.js': backendProxy,
        '/base.js':       backendProxy,
        '/download.js':   backendProxy,
        '/stat_var.js':   backendProxy,
      },
    },
  };
});
