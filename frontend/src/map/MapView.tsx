import type { JSX } from 'react';
import { useCallback, useMemo, useRef, useState } from 'react';
import { geoPath } from 'd3-geo';

import type { NetworkResponse, NodeWire } from '../api/types';
import { ClusterPopover } from './ClusterPopover';
import type { Cluster, ScreenPoint } from './clustering';
import { CLUSTER_THRESHOLD_PX, clusterByProximity } from './clustering';
import { landFeatures } from './landOutline';
import { NodeGlyph } from './NodeGlyph';
import { createProjection, MAP_HEIGHT, MAP_WIDTH } from './projection';
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
 * The map: a projection of the node positions over a faint land outline, pannable and
 * zoomable, with a popover for nodes that land close enough together on screen to not be
 * separately clickable otherwise.
 *
 * Geometry itself is the back end's job (D9); this component projects the coordinates it
 * is given with `d3-geo` and draws them. See `./projection.ts` for which projection and
 * why, and `./clustering.ts` for the popover's grouping rule.
 */
export function MapView({ network }: { network: NetworkResponse }): JSX.Element {
  const svgRef = useRef<SVGSVGElement | null>(null);
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

  const openNow = useCallback(
    (key: string) => {
      cancelClose();
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
      <div className="map-canvas">
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
                  <line
                    key={link.id}
                    className={`link link-${link.kind}`}
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
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
                    onMouseEnter={() => {
                      openNow(key);
                    }}
                    onMouseLeave={scheduleClose}
                    onFocus={() => {
                      if (suppressNextMarkerFocus.current) {
                        suppressNextMarkerFocus.current = false;
                        return;
                      }
                      openNow(key);
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
        {openCluster !== undefined ? (
          <ClusterPopover
            nodes={openCluster.members.map((member) => member.node)}
            anchorXPercent={(openCluster.x / MAP_WIDTH) * 100}
            anchorYPercent={(openCluster.y / MAP_HEIGHT) * 100}
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
