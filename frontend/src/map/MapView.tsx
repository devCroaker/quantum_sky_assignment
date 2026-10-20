import type { JSX } from 'react';
import { useCallback, useMemo, useRef, useState } from 'react';
import { geoPath } from 'd3-geo';

import type {
  CriticalityReason,
  CriticalityResponse,
  LinkKind,
  NetworkResponse,
  NodeWire,
  RankedLink,
} from '../api/types';
import { useHighlightHandlers } from '../state/selectionContext';
import { ClusterPopover } from './ClusterPopover';
import type { Cluster, ScreenPoint } from './clustering';
import { CLUSTER_THRESHOLD_PX, clusterByProximity } from './clustering';
import { Legend } from './Legend';
import { landFeatures } from './landOutline';
import { NodeGlyph } from './NodeGlyph';
import { createProjection, MAP_HEIGHT, MAP_WIDTH } from './projection';

/**
 * How close to the right edge a node must be before its label is drawn on the
 * other side. The longest id in the real data is OPS-SOUTHEAST, and at the label
 * font size that is comfortably under this width, so a flipped label stays on
 * the canvas. Without this a node near the right edge has its label clipped,
 * which is visible on first load before anyone has panned anywhere.
 */
const LABEL_FLIP_MARGIN = 150;
import { useZoomPan } from './useZoomPan';

/**
 * Above this zoom scale a backbone city earns a label too. Below it, only the nine sites
 * are labelled (see `shouldAlwaysLabel`), because at the default, zoomed-out view there is
 * not enough room between the 28 backbone cities to print every name without the text
 * overlapping into illegibility; the sites are few enough, and the ones the operations
 * reading needs most ("near what it attaches to", R9), to label from the start.
 */
const CITY_LABEL_ZOOM = 2.2;

/**
 * How long the popover waits, after the pointer leaves both the marker and the popover,
 * before it actually closes. The gap between a marker and its popover is empty space that
 * belongs to neither element, so a plain `onMouseLeave` on either one fires the instant
 * the pointer crosses it, and the popover would flicker shut and immediately reopen as the
 * pointer continues toward it. This delay turns "left the marker" into "might be heading
 * for the popover" and only commits to closing if neither element reports the pointer back
 * within it.
 */
const CLOSE_DELAY_MS = 150;

function shouldAlwaysLabel(kind: NodeWire['kind']): boolean {
  return kind !== 'backbone-city';
}

interface Projected extends ScreenPoint {
  readonly node: NodeWire;
}

/**
 * One link line, plus its D21 overlays: a dashed stroke and a reasons attribute when it is
 * critical, a rank badge and a heavier stroke when it is one of the five most utilized.
 *
 * A link needs its own component, rather than being built inline in the `network.links.map`
 * call the way it was before P17, because highlighting it is a hook
 * (`useHighlightHandlers`), and a hook cannot be called from inside an array callback.
 */
function LinkLine({
  id,
  kind,
  from,
  to,
  critical,
  reasons,
  rank,
}: {
  id: string;
  kind: LinkKind;
  from: { x: number; y: number };
  to: { x: number; y: number };
  critical: boolean;
  reasons: readonly CriticalityReason[];
  rank: number | undefined;
}): JSX.Element {
  const { highlighted, onPointerEnter, onPointerLeave, onSelect } = useHighlightHandlers({
    kind: 'link',
    id,
  });
  const classes = [`link`, `link-${kind}`];
  if (critical) classes.push('link-critical');
  if (rank !== undefined) classes.push('link-top-utilized');
  if (highlighted) classes.push('is-highlighted');
  const midpoint = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
  return (
    <>
      <line
        className={classes.join(' ')}
        data-link-id={id}
        data-critical-reasons={critical ? reasons.join(' ') : undefined}
        data-rank={rank}
        x1={from.x}
        y1={from.y}
        x2={to.x}
        y2={to.y}
        onMouseEnter={onPointerEnter}
        onMouseLeave={onPointerLeave}
        onClick={onSelect}
      >
        <title>
          {id}
          {critical ? ` (critical: ${reasons.join(', ')})` : ''}
          {rank !== undefined ? ` (rank ${String(rank)} of 5 most utilized)` : ''}
        </title>
      </line>
      {rank !== undefined ? (
        <g
          className="rank-badge"
          transform={`translate(${String(midpoint.x)},${String(midpoint.y)})`}
          aria-hidden="true"
        >
          <circle r={7} />
          <text y={3}>{rank}</text>
        </g>
      ) : null}
    </>
  );
}

/**
 * The map: a projection of the node positions over a faint land outline, pannable and
 * zoomable, with a popover for nodes that land close enough together on screen to not be
 * separately clickable otherwise.
 *
 * Geometry itself is the back end's job (D9); this component projects the coordinates it
 * is given with `d3-geo` and draws them. See `./projection.ts` for which projection and
 * why, and `./clustering.ts` for the popover's grouping rule.
 */
export function MapView({
  network,
  criticality,
  mostUtilized,
}: {
  network: NetworkResponse;
  /** R10: drives the critical-node ring/marker and critical-link dash. Undefined while
   * GET /api/v1/criticality has not resolved yet, which the map tolerates by drawing
   * nothing extra rather than waiting. */
  criticality?: CriticalityResponse;
  /** R10: ScenarioReport.most_utilized, already ranked by the server (D4). Undefined
   * before the baseline has loaded. */
  mostUtilized?: readonly RankedLink[];
}): JSX.Element {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const canvasRef = useRef<HTMLDivElement | null>(null);
  const [anchor, setAnchor] = useState<{ left: number; top: number } | null>(null);
  const { transform, onKeyDown } = useZoomPan(svgRef);
  const [openClusterKey, setOpenClusterKey] = useState<string | null>(null);
  const markerRefs = useRef(new Map<string, SVGGElement | null>());
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Escape closes the popover and hands focus back to its marker. That focus() call
  // raises a native focus event on an element whose onFocus normally *opens* the
  // popover, which would otherwise reopen it the instant it closed. This flag tells the
  // marker's onFocus "this focus was us returning it, not a Tab arriving", so it is set
  // immediately before that one focus() call and consumed by the very next focus event.
  const suppressNextMarkerFocus = useRef(false);

  const cancelClose = useCallback(() => {
    if (closeTimer.current !== null) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
  }, []);

  const scheduleClose = useCallback(() => {
    cancelClose();
    closeTimer.current = setTimeout(() => {
      setOpenClusterKey(null);
    }, CLOSE_DELAY_MS);
  }, [cancelClose]);

  // Measure the marker here rather than in an effect, because the element is
  // already in hand and a layout effect that calls setState triggers a cascading
  // render that the lint rules rightly object to.
  //
  // The anchor is measured rather than derived from the marker's viewBox
  // coordinates as a percentage of the canvas. Those are not the same thing: the
  // SVG preserves its aspect ratio, so whenever the canvas is a different shape
  // from the 960 by 640 viewBox the drawing is letterboxed inside it and a
  // percentage of the canvas lands somewhere the marker is not. Measuring also
  // makes the anchor correct under the zoom transform for free.
  const openNow = useCallback(
    (key: string, marker: SVGGElement | null) => {
      cancelClose();
      const canvas = canvasRef.current;
      if (marker !== null && canvas !== null) {
        const markerBox = marker.getBoundingClientRect();
        const canvasBox = canvas.getBoundingClientRect();
        setAnchor({
          left: markerBox.left - canvasBox.left + markerBox.width / 2,
          top: markerBox.top - canvasBox.top + markerBox.height / 2,
        });
      }
      setOpenClusterKey(key);
    },
    [cancelClose],
  );

  const projection = useMemo(
    () => createProjection(network.nodes, MAP_WIDTH, MAP_HEIGHT),
    [network.nodes],
  );
  const pathGenerator = useMemo(() => geoPath(projection), [projection]);
  const landPath = useMemo(() => pathGenerator(landFeatures), [pathGenerator]);

  // Base (pre-zoom) projected position for every node, keyed by id for the link endpoints.
  const basePositions = useMemo(() => {
    const positions = new Map<string, { x: number; y: number }>();
    for (const node of network.nodes) {
      const projected = projection([node.position.x, node.position.y]);
      if (projected === null) continue;
      positions.set(node.id, { x: projected[0], y: projected[1] });
    }
    return positions;
  }, [network.nodes, projection]);

  // Which nodes and links are critical, and why, keyed by id for an O(1) lookup while
  // drawing. Built once per criticality response rather than searched per element.
  const criticalNodes = useMemo(() => {
    const map = new Map<string, readonly CriticalityReason[]>();
    for (const assessment of criticality?.assessments ?? []) {
      if (assessment.kind === 'node' && assessment.critical) {
        map.set(assessment.id, assessment.reasons ?? []);
      }
    }
    return map;
  }, [criticality]);

  const criticalLinks = useMemo(() => {
    const map = new Map<string, readonly CriticalityReason[]>();
    for (const assessment of criticality?.assessments ?? []) {
      if (assessment.kind === 'link' && assessment.critical) {
        map.set(assessment.id, assessment.reasons ?? []);
      }
    }
    return map;
  }, [criticality]);

  // Rank (1 to 5) of a link id if it is among the five most utilized, server-ordered (D4):
  // the map never re-sorts or recomputes this, only looks it up.
  const rankByLinkId = useMemo(() => {
    const map = new Map<string, number>();
    for (const ranked of mostUtilized ?? []) {
      map.set(ranked.link_id, ranked.rank);
    }
    return map;
  }, [mostUtilized]);

  // Screen-space positions at the current zoom, which is what the clustering threshold is
  // defined against: two nodes far apart when zoomed out can separate once zoomed in, and
  // the grouping has to track that (the reviewer's "zoomed in, they separate" requirement).
  const projected = useMemo<Projected[]>(() => {
    const result: Projected[] = [];
    for (const node of network.nodes) {
      const base = basePositions.get(node.id);
      if (base === undefined) continue;
      result.push({
        id: node.id,
        x: transform.applyX(base.x),
        y: transform.applyY(base.y),
        node,
      });
    }
    return result;
  }, [network.nodes, basePositions, transform]);

  const clusters = useMemo<Cluster<Projected>[]>(
    () => clusterByProximity(projected, CLUSTER_THRESHOLD_PX),
    [projected],
  );

  const openCluster = clusters.find(
    (cluster) => clusterKey(cluster) === openClusterKey && cluster.members.length > 1,
  );

  return (
    <section className="map" aria-labelledby="map-heading">
      <h2 id="map-heading">Map</h2>
      <p className="placeholder-note">
        Pan: drag or arrow keys. Zoom: scroll, pinch, or +/-. Hover or focus a node that
        shows a count badge to see every node at that position.
      </p>
      <div className="map-canvas" ref={canvasRef}>
        <svg
          ref={svgRef}
          viewBox={`0 0 ${String(MAP_WIDTH)} ${String(MAP_HEIGHT)}`}
          className="map-svg"
          role="application"
          aria-label="Network map. Use arrow keys to pan and plus or minus to zoom."
          tabIndex={0}
          onKeyDown={onKeyDown}
        >
          <g
            transform={`translate(${String(transform.x)},${String(transform.y)}) scale(${String(transform.k)})`}
          >
            {landPath !== null ? <path d={landPath} className="land-outline" /> : null}
            <g className="links">
              {network.links.map((link) => {
                const [a, b] = link.endpoints;
                const from = basePositions.get(a);
                const to = basePositions.get(b);
                if (from === undefined || to === undefined) return null;
                return (
                  <LinkLine
                    key={link.id}
                    id={link.id}
                    kind={link.kind}
                    from={from}
                    to={to}
                    critical={criticalLinks.has(link.id)}
                    reasons={criticalLinks.get(link.id) ?? []}
                    rank={rankByLinkId.get(link.id)}
                  />
                );
              })}
            </g>
            <g className="nodes">
              {clusters.map((cluster) => {
                if (cluster.members.length === 1) {
                  const only = cluster.members[0];
                  if (only === undefined) return null;
                  const base = basePositions.get(only.id);
                  if (base === undefined) return null;
                  return (
                    <NodeGlyph
                      key={only.id}
                      id={only.id}
                      kind={only.node.kind}
                      x={base.x}
                      y={base.y}
                      label={
                        shouldAlwaysLabel(only.node.kind) || transform.k > CITY_LABEL_ZOOM
                      }
                      labelSide={
                        base.x > MAP_WIDTH - LABEL_FLIP_MARGIN ? 'left' : 'right'
                      }
                      critical={criticalNodes.has(only.id)}
                      reasons={criticalNodes.get(only.id) ?? []}
                    />
                  );
                }
                const key = clusterKey(cluster);
                // The marker sits at the cluster centroid in BASE coordinates: it lives
                // inside the same zoom-transformed `<g>` as everything else, so it pans
                // and scales with the map instead of needing its own transform math.
                const baseCentroid = baseCentroidOf(cluster, basePositions);
                return (
                  <g
                    key={key}
                    ref={(el) => {
                      markerRefs.current.set(key, el);
                    }}
                    className="cluster-marker"
                    transform={`translate(${String(baseCentroid.x)},${String(baseCentroid.y)})`}
                    tabIndex={0}
                    role="button"
                    aria-haspopup="menu"
                    aria-expanded={openClusterKey === key}
                    aria-label={`${String(cluster.members.length)} nodes at this position`}
                    onMouseEnter={(event) => {
                      openNow(key, event.currentTarget);
                    }}
                    onMouseLeave={scheduleClose}
                    onFocus={(event) => {
                      if (suppressNextMarkerFocus.current) {
                        suppressNextMarkerFocus.current = false;
                        return;
                      }
                      openNow(key, event.currentTarget);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === 'Escape') setOpenClusterKey(null);
                    }}
                  >
                    <title>{cluster.members.length} nodes here, open for details</title>
                    <circle className="cluster-marker-ring" r={11} />
                    {/*
                      The count is text, which is what makes this marker legible without
                      colour (D21): a reader sees "3" before ever hovering, not a dot that
                      only colour would have distinguished from a single node.
                    */}
                    <text className="cluster-marker-count" y={4}>
                      {cluster.members.length}
                    </text>
                  </g>
                );
              })}
            </g>
          </g>
        </svg>
        {openCluster !== undefined && anchor !== null ? (
          <ClusterPopover
            nodes={openCluster.members.map((member) => member.node)}
            anchorLeftPx={anchor.left}
            anchorTopPx={anchor.top}
            onClose={() => {
              setOpenClusterKey(null);
            }}
            onMouseEnter={cancelClose}
            onMouseLeave={scheduleClose}
            onSelectNode={() => {
              // P18 wires this to failing/selecting the node. No behaviour is asked of
              // R9 beyond the popover existing and each entry being a real, clickable
              // button, so this is deliberately a no-op for now.
            }}
            onRequestReturnFocus={() => {
              const key = openClusterKey;
              if (key === null) return;
              suppressNextMarkerFocus.current = true;
              markerRefs.current.get(key)?.focus();
            }}
          />
        ) : null}
      </div>
      <Legend />
    </section>
  );
}

function clusterKey(cluster: Cluster<Projected>): string {
  return cluster.members
    .map((member) => member.id)
    .slice()
    .sort()
    .join('+');
}

function baseCentroidOf(
  cluster: Cluster<Projected>,
  basePositions: Map<string, { x: number; y: number }>,
): { x: number; y: number } {
  const points = cluster.members
    .map((member) => basePositions.get(member.id))
    .filter((point): point is { x: number; y: number } => point !== undefined);
  if (points.length === 0) return { x: 0, y: 0 };
  return {
    x: points.reduce((sum, point) => sum + point.x, 0) / points.length,
    y: points.reduce((sum, point) => sum + point.y, 0) / points.length,
  };
}
