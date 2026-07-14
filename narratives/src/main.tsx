/**
 * @fileoverview Application entry point: mounts the React root into the DOM.
 */

import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import { App } from './app.tsx';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
