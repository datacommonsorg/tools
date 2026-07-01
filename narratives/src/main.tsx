/**
 * @fileoverview DOM entry point mounting the root React application onto the document.
 */

import {StrictMode} from 'react';
import {createRoot} from 'react-dom/client';
import { App } from './App';
import './index.css';

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
