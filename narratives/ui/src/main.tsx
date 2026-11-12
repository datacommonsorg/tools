/**
 * @fileoverview Application entry point: mounts the React root into the DOM.
 */

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from '@/src/app';
import { registerViewTransitionFilter } from '@/src/utils/view_transition';
import '@/src/index.css';

registerViewTransitionFilter();

const root = document.getElementById('root');
if (!root) throw new Error('index.html has no #root element.');

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
