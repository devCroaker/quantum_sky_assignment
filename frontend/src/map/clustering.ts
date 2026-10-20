/**
 * Screen-space grouping for the cluster popover the reviewer asked for.
 *
 * The back end now gives every node a distinct coordinate (another agent is adding a
 * small deterministic offset so genuinely coincident sites separate), so this module must
 * not rely on positions ever being exactly equal. Instead it groups whatever is close
 * enough on screen, at the current zoom, to be indistinguishable to a pointer or a reader.
 */

/**
 * How close two projected points must be, in SVG user units (the map's `viewBox` is
 * `MAP_WIDTH` by `MAP_HEIGHT`, so a unit is treated as roughly a CSS pixel at the map's
 * natural size), to be folded into one cluster.
 *
 * 24 is WCAG 2.5.8's minimum target size (24 by 24 CSS pixels). Below that gap there is
 * already no reliable way to aim a pointer, or a screen reader's touch cursor, at one node
 * and not its neighbour, so two points closer than this are indistinguishable targets
 * regardless of how carefully they are drawn, and grouping them behind one popover is the
 * only affordance that is actually operable.
 */
export const CLUSTER_THRESHOLD_PX = 24;

export interface ScreenPoint {
  readonly id: string;
  readonly x: number;
  readonly y: number;
}

export interface Cluster<T extends ScreenPoint> {
  /** Centroid of the member points, where the marker and the popover anchor. */
  readonly x: number;
  readonly y: number;
  readonly members: readonly T[];
}

function findRoot(parents: readonly number[], start: number): number {
  let current = start;
  for (;;) {
    const next = parents[current];
    if (next === undefined) {
      throw new Error(`clustering: index ${String(current)} out of range`);
    }
    if (next === current) return current;
    current = next;
  }
}

/**
 * Union-find over the pairwise "closer than the threshold" relation, so that three nodes
 * each within range of their neighbour but not of each other (a short chain) still end up
 * in one cluster, which is what "indistinguishable as separate targets" requires: the
 * relation is not transitive geometrically, but the inability to pick between neighbours
 * is.
 */
export function clusterByProximity<T extends ScreenPoint>(
  points: readonly T[],
  thresholdPx: number = CLUSTER_THRESHOLD_PX,
): Cluster<T>[] {
  const parents = points.map((_, index) => index);

  function union(a: number, b: number): void {
    const rootA = findRoot(parents, a);
    const rootB = findRoot(parents, b);
    if (rootA !== rootB) parents[rootA] = rootB;
  }

  for (let i = 0; i < points.length; i += 1) {
    for (let j = i + 1; j < points.length; j += 1) {
      const a = points[i];
      const b = points[j];
      if (a === undefined || b === undefined) continue;
      if (Math.hypot(a.x - b.x, a.y - b.y) <= thresholdPx) union(i, j);
    }
  }

  const groups = new Map<number, T[]>();
  points.forEach((point, index) => {
    const root = findRoot(parents, index);
    const existing = groups.get(root);
    if (existing === undefined) groups.set(root, [point]);
    else existing.push(point);
  });

  return Array.from(groups.values()).map((members) => ({
    x: members.reduce((sum, member) => sum + member.x, 0) / members.length,
    y: members.reduce((sum, member) => sum + member.y, 0) / members.length,
    members,
  }));
}
