/**
 * @fileoverview Application entry point: mounts the React root into the DOM.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@/src/app';
import { getRuntimeConfig } from '@/src/config/runtime_config';
import { loadWebComponents } from '@/src/utils/load_web_components';
import { registerViewTransitionFilter } from '@/src/utils/view_transition';
import '@/src/index.css';

registerViewTransitionFilter();
loadWebComponents(getRuntimeConfig().webComponentUrl);

const root = document.getElementById('root');
if (!root) throw new Error('index.html has no #root element.');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
