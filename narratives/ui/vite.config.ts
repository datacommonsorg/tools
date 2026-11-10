/// <reference types="vite/client" />
/// <reference types="vitest" />

import path from 'node:path';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig, loadEnv, type Plugin } from 'vite';
import {
  copyAgentRuntimeConfig,
  resolveAgentShellUrl,
} from './src/config/runtime_config_dev';

// Dev-proxy default for a local agent.
const DEFAULT_AGENT_URL = 'http://localhost:5001';

/**
 * Copies the agent's chat availability into `#runtime-config` each time the
 * Vite dev server serves index.html, reading the shell the agent at
 * `agentShellUrl` stamps, so the agent stays the only source of truth.
 * `apply: 'serve'` keeps it out of `vite build`, so the built index.html
 * keeps the empty slot for the agent to stamp.
 */
const createRuntimeConfigDevPlugin = (agentShellUrl: string): Plugin => ({
  name: 'narratives-runtime-config',
  apply: 'serve',
  transformIndexHtml: (html) => copyAgentRuntimeConfig(html, agentShellUrl),
});

export default defineConfig(({ command, mode }) => {
  const envDir = path.resolve(__dirname, '..');
  // Load environment variables from narratives/.env.local
  const env = loadEnv(mode, envDir, '');
  // Production builds emit `./` asset and chunk paths so one image serves at `/`
  // or under any runtime `BASE_PATH`; `vite dev` keeps `/` for the `/agent` proxy.
  const base = command === 'build' ? './' : '/';
  const agentTarget = env.AGENT_URL || DEFAULT_AGENT_URL;
  // `/agent/*` forwards to AGENT_URL's own path, and the agent's HTML shell
  // lives at that same path.
  const agentShellUrl = resolveAgentShellUrl(agentTarget);
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
      ? { rewrite: (urlPath: string) => urlPath.replace(/^\/agent/, '') }
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
    plugins: [
      react(),
      tailwindcss(),
      createRuntimeConfigDevPlugin(agentShellUrl),
    ],
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
