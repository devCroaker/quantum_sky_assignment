import { describe, expect, it } from 'vitest';

import { CLUSTER_THRESHOLD_PX, clusterByProximity } from '../../map/clustering';

describe('clusterByProximity', () => {
  it('groups two points within the threshold into one cluster', () => {
    const points = [
      { id: 'a', x: 100, y: 100 },
      { id: 'b', x: 100 + CLUSTER_THRESHOLD_PX - 1, y: 100 },
    ];

    const clusters = clusterByProximity(points);

    expect(clusters).toHaveLength(1);
    expect(clusters[0]?.members.map((m) => m.id).sort()).toEqual(['a', 'b']);
  });

  it('keeps the same two points separate once they are beyond the threshold', () => {
    const points = [
      { id: 'a', x: 100, y: 100 },
      { id: 'b', x: 100 + CLUSTER_THRESHOLD_PX + 1, y: 100 },
    ];

    const clusters = clusterByProximity(points);

    expect(clusters).toHaveLength(2);
    for (const cluster of clusters) {
      expect(cluster.members).toHaveLength(1);
    }
  });

  it('chains a transitive cluster: a close to b, b close to c, a far from c', () => {
    // a-b and b-c are each within the threshold, a-c is not. If a reader can't tell a
    // from b, and can't tell b from c, they effectively can't tell a from c either, even
    // though a and c are individually far enough apart that a direct comparison would say
    // otherwise. The popover needs all three listed together, not two overlapping pairs.
    const step = CLUSTER_THRESHOLD_PX - 1;
    const points = [
      { id: 'a', x: 0, y: 0 },
      { id: 'b', x: step, y: 0 },
      { id: 'c', x: step * 2, y: 0 },
    ];

    const clusters = clusterByProximity(points);

    expect(clusters).toHaveLength(1);
    expect(clusters[0]?.members).toHaveLength(3);
  });

  it('places the cluster marker at the centroid of its members', () => {
    const points = [
      { id: 'a', x: 0, y: 0 },
      { id: 'b', x: 10, y: 20 },
    ];

    const [cluster] = clusterByProximity(points, 50);

    expect(cluster?.x).toBe(5);
    expect(cluster?.y).toBe(10);
  });
});
