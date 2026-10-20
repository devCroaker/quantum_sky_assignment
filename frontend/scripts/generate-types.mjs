// Generates src/api/types.ts from contracts/schema.json.
//
// The wire types are generated rather than hand-maintained, so the two sides of the wire
// cannot drift apart. Run with no arguments to write the file, or with --check to verify
// that the committed file still matches the schema. The same comparison runs as a Vitest
// case, so a stale type file fails the suite rather than only a separate command.
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import { compile } from 'json-schema-to-typescript';

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = resolve(here, '..');

export const schemaPath = resolve(frontendRoot, '../contracts/schema.json');
export const outputPath = resolve(frontendRoot, 'src/api/types.ts');

const banner = [
  '/**',
  ' * GENERATED FILE. DO NOT EDIT BY HAND.',
  ' *',
  ' * Produced from contracts/schema.json by `npm run types`.',
  ' * `npm run types:check` and src/test/generated-types.test.ts both fail when this',
  ' * file no longer matches the schema. Change the Pydantic models and regenerate.',
  ' */',
].join('\n');

/**
 * Rewrite the 2020-12 constructs the generator does not understand, in place.
 *
 * Two shims, both deterministic and both a translation rather than a change of meaning:
 *
 * 1. `prefixItems` is the 2020-12 spelling of a tuple. The generator still reads the
 *    draft-07 spelling, an array-valued `items`, and without this it emits
 *    `[unknown, unknown]` for every sorted endpoint pair.
 * 2. Pydantic gives every field a `title`, and the generator turns each one into its own
 *    exported alias, so `LinkWire.id` would arrive as `Id1` and `ErrorDetail.file` as a
 *    type named `File`. Dropping the titles of property subschemas, and only those,
 *    leaves the inline primitive in place. The titles on the `$defs` entries are kept,
 *    because those are the names of the interfaces we actually want.
 */
function adaptForGenerator(node, insideProperties = false) {
  if (Array.isArray(node)) {
    for (const item of node) adaptForGenerator(item, insideProperties);
    return;
  }
  if (node === null || typeof node !== 'object') return;

  if (Array.isArray(node.prefixItems) && node.items === undefined) {
    node.items = node.prefixItems;
    delete node.prefixItems;
  }
  if (insideProperties && typeof node.title === 'string') {
    delete node.title;
  }

  for (const [key, value] of Object.entries(node)) {
    adaptForGenerator(value, insideProperties || key === 'properties');
  }
}

/** Compile the committed contract schema to TypeScript source text. */
export async function renderTypes() {
  const schema = JSON.parse(await readFile(schemaPath, 'utf8'));
  adaptForGenerator(schema);
  return compile(schema, 'NetscopeContract', {
    bannerComment: banner,
    // Every wire type lives in $defs and is unreachable from the root, which carries
    // only the endpoint table. Without this, nothing at all would be emitted.
    unreachableDefinitions: true,
    declareExternallyReferenced: true,
    additionalProperties: false,
    style: { singleQuote: true },
  });
}

async function main() {
  const rendered = await renderTypes();
  if (!process.argv.includes('--check')) {
    await writeFile(outputPath, rendered, 'utf8');
    console.log(`wrote ${outputPath}`);
    return;
  }

  const committed = await readFile(outputPath, 'utf8');
  if (committed === rendered) {
    console.log('src/api/types.ts is up to date');
    return;
  }

  // Keep the fresh output on disk so a reviewer can diff the two by hand.
  const scratch = join(await mkdtemp(join(tmpdir(), 'netscope-types-')), 'types.ts');
  await writeFile(scratch, rendered, 'utf8');
  console.error(
    'src/api/types.ts is stale. Regenerate it with `npm run types`.\n' +
      `Fresh output written to ${scratch} for comparison.`,
  );
  process.exitCode = 1;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await main();
}
