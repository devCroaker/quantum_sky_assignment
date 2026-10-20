import { describe, expect, it } from 'vitest';

import networkFixture from '@contracts/fixtures/network.json';

import { parseNetworkResponse } from '../../api/guards';
import { createProjection, MAP_HEIGHT, MAP_WIDTH } from '../../map/projection';

const fixture = parseNetworkResponse(networkFixture);

function project(id: string): readonly [number, number] {
  const node = fixture.nodes.find((candidate) => candidate.id === id);
  if (node === undefined) throw new Error(`fixture has no node ${id}`);
  const projection = createProjection(fixture.nodes, MAP_WIDTH, MAP_HEIGHT);
  const point = projection([node.position.x, node.position.y]);
  if (point === null) throw new Error(`${id} failed to project`);
  return [point[0], point[1]];
}

describe('the Europe projection', () => {
  // These are real SNDlib coordinates (position.x is longitude, position.y is latitude,
  // per docs/api-contract.md). Getting the two the wrong way round would not necessarily
  // error, since geoAzimuthalEqualArea happily projects any pair of numbers; it would
  // instead scramble these relationships below, which is exactly what should fail here
  // rather than being caught by eye on the rendered map.
  it('keeps Warsaw east of Hamburg', () => {
    const [warsawX] = project('Warsaw');
    const [hamburgX] = project('Hamburg');
    expect(warsawX).toBeGreaterThan(hamburgX);
  });

  it('keeps Copenhagen north of Berlin (smaller y is further up the page)', () => {
    const [, copenhagenY] = project('Copenhagen');
    const [, berlinY] = project('Berlin');
    expect(copenhagenY).toBeLessThan(berlinY);
  });

  it('keeps every fixture node inside the viewBox', () => {
    for (const node of fixture.nodes) {
      const projection = createProjection(fixture.nodes, MAP_WIDTH, MAP_HEIGHT);
      const point = projection([node.position.x, node.position.y]);
      expect(point).not.toBeNull();
      const [x, y] = point as [number, number];
      expect(x).toBeGreaterThanOrEqual(0);
      expect(x).toBeLessThanOrEqual(MAP_WIDTH);
      expect(y).toBeGreaterThanOrEqual(0);
      expect(y).toBeLessThanOrEqual(MAP_HEIGHT);
    }
  });

  // A change-detector for the projection itself: any edit to the projection family, the
  // rotation, the padding, or the fit logic in src/map/projection.ts shows up here as a
  // diff for review, rather than only as a silent shift on the rendered map. The values
  // are not hand-invented; they are whatever createProjection, the function under test,
  // produces today, captured once as a snapshot.
  it('projects Berlin to a stable pixel position', () => {
    expect(project('Berlin')).toMatchInlineSnapshot(`
      [
        260.2316890856604,
        481.73584497252506,
      ]
    `);
  });
});
