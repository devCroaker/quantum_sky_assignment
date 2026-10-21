import type { JSX } from 'react';

import type { CriticalityReason, NodeKind } from '../api/types';
import { useFailureToggle } from '../state/failureContext';
import { useHighlightHandlers } from '../state/selectionContext';
import { glyphShapeFor, kindLabelFor } from './nodeKind';

/** Radius/half-width used so the four shapes read as roughly the same visual size. */
const GLYPH_SIZE = 7;

/** Radius of the dashed ring drawn around a critical node (D21). Large enough to clear
 * every glyph shape, including the diamond, which is the widest at this size. */
const CRITICAL_RING_RADIUS = GLYPH_SIZE + 6;

/** Half-width of the cross drawn over a failed node. Inside the glyph, not around it, so a
 * failed node is never mistaken for a critical one, whose marks sit outside the shape. */
const FAILED_CROSS_HALF = GLYPH_SIZE * 0.7;

/**
 * A small warning triangle, offset to the glyph's upper right, so a critical node reads as
 * "shape plus marker" rather than only "shape in a ring". D21 asks for both the ring and a
 * warning marker on critical nodes; the ring alone would be easy to miss against the
 * cluster-marker ring style, which also uses a dashed circle.
 */
function WarningMarker(): JSX.Element {
  const offset = GLYPH_SIZE + 4;
  return (
    <g
      className="critical-marker"
      transform={`translate(${String(offset)},${String(-offset)})`}
    >
      <polygon className="critical-marker-triangle" points="0,-5 4.3,3 -4.3,3" />
      <text className="critical-marker-bang" y={2.4}>
        !
      </text>
    </g>
  );
}

/**
 * A cross over a failed node. A failed node is faded and crossed out, which shares no shape
 * with the dashed ring and the warning triangle that mark a critical one, so the two cannot
 * be confused in greyscale (D21).
 */
export function FailedCross({
  half = FAILED_CROSS_HALF,
}: {
  half?: number;
}): JSX.Element {
  const d = `M${String(-half)},${String(-half)} L${String(half)},${String(half)} M${String(half)},${String(-half)} L${String(-half)},${String(half)}`;
  return (
    <g className="failed-marker" aria-hidden="true">
      <path d={d} />
    </g>
  );
}

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
 *
 * Clicking, or pressing Enter or Space on it, fails or restores the node (R11). A failed
 * node carries `data-failed="true"`, fades its shape and is crossed out.
 */
export function NodeGlyph({
  id,
  kind,
  x,
  y,
  label,
  labelSide = 'right',
  critical = false,
  reasons = [],
}: {
  id: string;
  kind: NodeKind;
  x: number;
  y: number;
  /** Whether to draw the text label next to the glyph. */
  label: boolean;
  /**
   * Which side of the glyph the label sits on. A label is drawn to the right by
   * default, which runs it off the canvas for a node near the right edge. The
   * caller flips the side rather than this component guessing, because only the
   * caller knows the width it is drawing into.
   */
  labelSide?: 'left' | 'right';
  /** R7/R10: true when this node is a single point of failure under any reason. */
  critical?: boolean;
  /**
   * Which R7 reasons apply. Carried as the `data-critical-reasons` DOM attribute so a test
   * (and a future export) can read why a node is marked without inferring it from a ring
   * that greyscale, a bad projector or colour blindness could just as easily hide (D21).
   */
  reasons?: readonly CriticalityReason[];
}): JSX.Element {
  const { highlighted, onPointerEnter, onPointerLeave, onFocus, onBlur, onSelect } =
    useHighlightHandlers({ kind: 'node', id });
  const { failed, toggle, onKeyDown } = useFailureToggle({ kind: 'node', id });
  const classes = ['node-glyph'];
  if (critical) classes.push('node-glyph-critical');
  if (failed) classes.push('node-glyph-failed');
  if (highlighted) classes.push('is-highlighted');
  const criticalText = critical ? `critical: ${reasons.join(', ')}` : '';
  const failedText = failed ? 'failed' : '';
  const stateText = [criticalText, failedText].filter((part) => part !== '').join(', ');
  return (
    <g
      className={classes.join(' ')}
      data-node-id={id}
      data-shape={glyphShapeFor(kind)}
      data-critical-reasons={critical ? reasons.join(' ') : undefined}
      data-failed={failed ? 'true' : undefined}
      transform={`translate(${String(x)},${String(y)})`}
      tabIndex={0}
      role="button"
      aria-pressed={failed}
      aria-label={
        stateText === ''
          ? `${id}, ${kindLabelFor(kind)}`
          : `${id}, ${kindLabelFor(kind)}, ${stateText}`
      }
      onMouseEnter={onPointerEnter}
      onMouseLeave={onPointerLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={() => {
        onSelect();
        toggle();
      }}
      onKeyDown={onKeyDown}
    >
      <title>
        {id} ({kindLabelFor(kind)}){failed ? ', failed' : ''}
      </title>
      {critical ? <circle className="critical-ring" r={CRITICAL_RING_RADIUS} /> : null}
      <g className={failed ? 'node-body node-body-failed' : 'node-body'}>
        <ShapePath kind={kind} />
      </g>
      {failed ? <FailedCross /> : null}
      {critical ? <WarningMarker /> : null}
      {label ? (
        <text
          className="node-label"
          x={labelSide === 'left' ? -(GLYPH_SIZE + 4) : GLYPH_SIZE + 4}
          y={4}
          textAnchor={labelSide === 'left' ? 'end' : 'start'}
        >
          {id}
        </text>
      ) : null}
    </g>
  );
}
