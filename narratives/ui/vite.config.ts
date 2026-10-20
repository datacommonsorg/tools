/// <reference types="vite/client" />
/// <reference types="vitest" />
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';
import {normalizeBasePath} from './src/config/base_url';

// Dev-proxy default for a local agent.
const DEFAULT_AGENT_URL = 'http://localhost:5001';

export default defineConfig(({mode}) => {
  const envDir = path.resolve(__dirname, '..');
  // Load environment variables from narratives/.env.local
  const env = loadEnv(mode, envDir, '');
  const base = normalizeBasePath(env.VITE_BASE_PATH);
  const agentTarget = env.AGENT_URL || DEFAULT_AGENT_URL;
  // By default, the agent serves its API under /agent (AGENT_API_PREFIX), so
  // /agent/* requests are forwarded verbatim to AGENT_URL, whether a local
  // agent or a deployed instance.
  //
  // Set AGENT_STRIP_PREFIX=true in .env.local only when the agent serves its
  // API at the root (AGENT_API_PREFIX=/). An empty AGENT_API_PREFIX counts as
  // unset and selects /agent.
  const agentProxy = {
    target: agentTarget,
    changeOrigin: true,
    ...(env.AGENT_STRIP_PREFIX === 'true'
      ? {rewrite: (urlPath: string) => urlPath.replace(/^\/agent/, '')}
      : {}),
  };
  return {
    base,
    envDir,
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
      // Path A (UI + remote agent): set AGENT_URL in .env.local.
      // Path B (full local stack):  defaults target localhost:5001.
      // server.proxy is dev-only - `vite build` ignores it, so production is unaffected.
      proxy: {
        // Match the `/agent` path segment without capturing `/agent*` public assets.
        '^/agent([/?]|$)': agentProxy,
      },
    },
  };
});
