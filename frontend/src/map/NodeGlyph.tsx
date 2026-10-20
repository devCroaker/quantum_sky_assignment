import type { JSX } from 'react';

import type { NodeKind } from '../api/types';
import { glyphShapeFor, kindLabelFor } from './nodeKind';

/** Radius/half-width used so the four shapes read as roughly the same visual size. */
const GLYPH_SIZE = 7;

/** Builds an SVG `points` attribute value from numeric coordinate pairs. */
function points(coords: ReadonlyArray<readonly [number, number]>): string {
  return coords.map(([x, y]) => `${String(x)},${String(y)}`).join(' ');
}

function ShapePath({ kind }: { kind: NodeKind }): JSX.Element {
  const r = GLYPH_SIZE;
  switch (kind) {
    case 'backbone-city':
      return <circle r={r} />;
    case 'data-center':
      return <rect x={-r} y={-r} width={r * 2} height={r * 2} />;
    case 'operations-site':
      return (
        <polygon
          points={points([
            [0, -r * 1.15],
            [r * 1.1, r * 0.8],
            [-r * 1.1, r * 0.8],
          ])}
        />
      );
    case 'aggregation-hub':
      return (
        <polygon
          points={points([
            [0, -r * 1.3],
            [r * 1.3, 0],
            [0, r * 1.3],
            [-r * 1.3, 0],
          ])}
        />
      );
  }
}

/**
 * One node glyph, shape keyed by `kind` (R9, D21). `x`/`y` are already in the zoomed SVG
 * user space; the caller applies the pan/zoom transform to the enclosing `<g>`.
 */
export function NodeGlyph({
  id,
  kind,
  x,
  y,
  label,
}: {
  id: string;
  kind: NodeKind;
  x: number;
  y: number;
  /** Whether to draw the text label next to the glyph. */
  label: boolean;
}): JSX.Element {
  return (
    <g
      className="node-glyph"
      data-node-id={id}
      data-shape={glyphShapeFor(kind)}
      transform={`translate(${String(x)},${String(y)})`}
      tabIndex={0}
      role="button"
      aria-label={`${id}, ${kindLabelFor(kind)}`}
    >
      <title>
        {id} ({kindLabelFor(kind)})
      </title>
      <ShapePath kind={kind} />
      {label ? (
        <text className="node-label" x={GLYPH_SIZE + 4} y={4}>
          {id}
        </text>
      ) : null}
    </g>
  );
}
