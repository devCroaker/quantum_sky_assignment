import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import { dataSource } from './api';
import { App } from './app/App';
import './styles/global.css';

const container = document.getElementById('root');
if (container === null) {
  // Preferred over a non-null assertion, which CLAUDE.md forbids.
  throw new Error('index.html is missing the #root element');
}

createRoot(container).render(
  <StrictMode>
    <App source={dataSource} />
  </StrictMode>,
);
