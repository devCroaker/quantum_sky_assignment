import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

// Testing Library only auto-cleans when the test globals are injected, and they are not.
afterEach(cleanup);
