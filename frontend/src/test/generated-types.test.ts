// @vitest-environment node
import { readFile } from 'node:fs/promises';

import { describe, expect, it } from 'vitest';

// The generator exports its render step so that the staleness check is a test case and
// not only a separate command. CI runs lint, typecheck and the suite but not
// `npm run types:check`, so without this a stale types.ts could reach main unnoticed.
import { outputPath, renderTypes } from '../../scripts/generate-types.mjs';

describe('the generated wire types', () => {
  it('match contracts/schema.json', async () => {
    const fresh = await renderTypes();
    const committed = await readFile(outputPath, 'utf8');
    expect(committed).toBe(fresh);
  });
});
