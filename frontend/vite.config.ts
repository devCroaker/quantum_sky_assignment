import { fileURLToPath } from 'node:url';

import react from '@vitejs/plugin-react';
// Imported from vitest/config rather than vite so that the test block below is typed.
// Vitest reads this same file, which is why resolve.alias covers dev, build and tests
// from one definition instead of three that could drift.
import { defineConfig } from 'vitest/config';

// The committed fixtures live in contracts/, one level above this package, because they
// are generated from the back end's Pydantic models and belong to neither half alone.
// Vite refuses to serve a file from outside the project root unless it is listed in
// server.fs.allow, so the alias alone is not enough.
const contractsDir = fileURLToPath(new URL('../contracts', import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@contracts': contractsDir,
    },
  },
  server: {
    fs: {
      allow: ['.', contractsDir],
    },
    proxy: {
      // The back end runs separately during development. Keeping the view on a single
      // origin means no CORS configuration and no absolute URLs in the data layer.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: false,
    setupFiles: ['./vitest.setup.ts'],
    include: ['src/**/*.test.ts', 'src/**/*.test.tsx'],
  },
});
