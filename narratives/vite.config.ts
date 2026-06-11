import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import {defineConfig, loadEnv} from 'vite';

export default defineConfig(({mode}) => {
  const env = loadEnv(mode, '.', '');
  return {
    plugins: [react(), tailwindcss()],
    define: {},
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
        '/api':     { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/mcp':     { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/place':   { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/browser': { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/explore': { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/core':    { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/agent':   { target: env.AGENT_URL   || 'http://localhost:5001', changeOrigin: true },
        // /tools/* paths host upstream Flask-rendered pages we iframe — currently
        // /tools/download. /css, /custom_dc, /queryStore.js, /base.js, /download.js
        // and friends are the absolute-path assets those pages reference. All
        // routed to BACKEND_URL so the iframe behaves identically in dev and in
        // the baked production image (where nginx covers the same paths).
        '/tools':         { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/css':           { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/custom_dc':     { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/queryStore.js': { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/base.js':       { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/download.js':   { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
        '/stat_var.js':   { target: env.BACKEND_URL || 'http://localhost:8080', changeOrigin: true },
      },
    },
  };
});
