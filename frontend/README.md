# netscope front end

The map and panels for the network analysis tool. Vite, React and TypeScript in strict
mode, with hand-rolled CSS and no component library, so that every visual decision can be
explained to the panel.

This package is the P15 scaffold. The map (P16), the criticality and utilization overlays
(P17) and the failure interaction (P18) are placeholders with a comment naming the task
that fills them.

## Running it

From the repository root, `make install` installs both halves. Then, from here:

| Command | What it does |
| --- | --- |
| `npm run dev` | Vite dev server |
| `npm run build` | Production build |
| `npm run preview` | Serve the production build |
| `npm run lint` | ESLint, which also enforces Prettier formatting |
| `npm run typecheck` | `tsc --noEmit` |
| `npm test` | Vitest, watching. `npm test -- --run` for one pass |
| `npm run types` | Regenerate `src/api/types.ts` from `contracts/schema.json` |
| `npm run types:check` | Fail if the committed `src/api/types.ts` is stale |

`make check` from the root runs lint, typecheck and the test suite for both halves. Those
are the same three commands CI runs.

## Choosing a data source

The back end endpoints do not exist yet, so the application runs entirely on the payloads
committed in `contracts/fixtures/`. `VITE_DATA_SOURCE` selects which implementation of
`NetworkDataSource` is used:

| Value | Behaviour |
| --- | --- |
| `fixture` (the default) | Reads the committed fixtures. No back end needed |
| `live` | Calls the four endpoints in `docs/api-contract.md` under `/api` |

An unset or empty variable means `fixture`, so a fresh checkout runs with nothing else
started. Any other value is an error at startup rather than a silent fallback.

```sh
npm run dev                            # fixture mode
VITE_DATA_SOURCE=live npm run dev      # live mode, with the API on 127.0.0.1:8000
```

In live mode the dev server proxies `/api` to `http://127.0.0.1:8000`, so the browser only
ever talks to its own origin and there is no CORS configuration to get wrong.

### What fixture mode can and cannot answer

`contracts/fixtures/` holds a `NetworkResponse` and two `ScenarioReport` payloads, for the
baseline and for Berlin failed. So the fixture source answers:

- `network()` and `baseline()`, always
- `scenario()` for an empty failed set, returning the baseline
- `scenario()` for exactly the node `Berlin`

Everything else, including `criticality()`, rejects with a message saying it is not
available in fixture mode. It would be easy to return the baseline for any request and
much worse: failing Hamburg would appear to change nothing, and nobody would know whether
that was the fixture or a bug.

## How the wire types are produced

`src/api/types.ts` is generated from `contracts/schema.json`, which is itself generated
from the back end's Pydantic models. Never edit it by hand. It carries a banner saying so,
`npm run types:check` fails when it is stale, and so does
`src/test/generated-types.test.ts`, because CI runs the test suite but not every script.

## Shape of the code

```
src/
  api/        the data layer: generated types, hand-written guards, two sources
  app/        the shell, map left at two thirds and a persistent panel right at one third
  map/        placeholder for P16
  panels/     the three side panel sections, placeholders for P17 and P18
  styles/     the whole stylesheet
  test/       the suite
```

Every payload is checked by the narrow guards in `src/api/guards.ts` before any component
sees it, whether it came from a fixture or from the network. A malformed payload throws a
`WireFormatError` naming the field, at the boundary, rather than appearing as an undefined
inside a component during a demonstration. There is no runtime validation library: the
guards are mechanical and short enough to read.

The `@contracts` alias points at the repository-level `contracts/` directory, which sits
outside this package. It is declared in three places that have to agree: `resolve.alias`
in `vite.config.ts` (which Vitest reads from the same file), `compilerOptions.paths` in
`tsconfig.json`, and `server.fs.allow`, without which the dev server refuses to serve a
file from outside the project root.
