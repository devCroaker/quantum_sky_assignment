import baselineFixture from '@contracts/fixtures/baseline.json';
import criticalityFixture from '@contracts/fixtures/criticality.json';
import networkFixture from '@contracts/fixtures/network.json';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  parseCriticalityResponse,
  parseNetworkResponse,
  parseScenarioReport,
} from '../../api/guards';
import type { NetworkResponse } from '../../api/types';
import { MapView } from '../../map/MapView';
import { SelectionProvider } from '../../state/selection';

const criticality = parseCriticalityResponse(criticalityFixture);
const baseline = parseScenarioReport(baselineFixture);

/**
 * A cluster absorbs its members' glyphs, so a critical node inside one would
 * disappear from the map entirely unless the marker says otherwise.
 *
 * This is not hypothetical. On the real network the three eastern nodes sit
 * about 11 pixels apart at the default view, well inside the clustering
 * threshold, and one of them is HUB-EAST, which is one of only four nodes whose
 * loss partitions the network. Without this the map would quietly hide the very
 * finding the tool exists to surface, and the Critical panel would list an
 * element the map does not mark.
 *
 * The committed fixture does not cluster, so the network here is built by moving
 * one node onto another. That is the only way to exercise the case, and it is
 * why this test fabricates its input rather than reading it.
 */
function coLocatedNetwork(): NetworkResponse {
  const base = parseNetworkResponse(networkFixture);
  const hub = base.nodes.find((node) => node.id === 'HUB-EAST');
  if (hub === undefined) throw new Error('fixture changed: HUB-EAST is missing');

  return {
    ...base,
    nodes: base.nodes.map((node) =>
      node.id === 'OPS-EAST-1'
        ? { ...node, position: { x: hub.position.x + 0.02, y: hub.position.y + 0.02 } }
        : node,
    ),
  };
}

describe('a cluster containing a critical node', () => {
  it('carries its members reasons and a non-colour marker', () => {
    const { container } = render(
      <SelectionProvider>
        <MapView
          network={coLocatedNetwork()}
          criticality={criticality}
          mostUtilized={baseline.most_utilized}
        />
      </SelectionProvider>,
    );

    const marker = container.querySelector('.cluster-marker');
    expect(marker).not.toBeNull();

    // HUB-EAST is critical and OPS-EAST-1 is not, so the marker must carry
    // HUB-EAST's reasons and count exactly one critical member. Taking the union
    // is what makes that work without the marker having to know which member
    // mattered.
    const reasons = marker?.getAttribute('data-critical-reasons')?.split(' ') ?? [];
    const expected = new Set(
      ['HUB-EAST', 'OPS-EAST-1'].flatMap(
        (id) =>
          criticality.assessments.find((a) => a.kind === 'node' && a.id === id)
            ?.reasons ?? [],
      ),
    );
    expect(new Set(reasons)).toEqual(expected);
    expect(marker?.getAttribute('data-critical-members')).toBe('1');

    // D21: the meaning must survive greyscale, so shape carries it too.
    expect(marker?.querySelector('.critical-ring')).not.toBeNull();
    expect(marker?.querySelector('.critical-marker')).not.toBeNull();
  });

  it('leaves a cluster of non-critical nodes unmarked', () => {
    const base = parseNetworkResponse(networkFixture);
    const copenhagen = base.nodes.find((node) => node.id === 'Copenhagen');
    const hamburg = base.nodes.find((node) => node.id === 'Hamburg');
    if (copenhagen === undefined || hamburg === undefined) {
      throw new Error('fixture changed: expected Copenhagen and Hamburg');
    }
    // Neither Copenhagen nor Hamburg is critical: Copenhagen costs nothing when
    // lost and Hamburg costs only its own traffic, which R7 no longer counts.
    // A cluster of the two must therefore carry no criticality marking at all.
    const network: NetworkResponse = {
      ...base,
      nodes: base.nodes.map((node) =>
        node.id === 'Copenhagen'
          ? { ...node, position: { x: hamburg.position.x + 0.02, y: hamburg.position.y } }
          : node,
      ),
    };

    const { container } = render(
      <SelectionProvider>
        <MapView
          network={network}
          criticality={criticality}
          mostUtilized={baseline.most_utilized}
        />
      </SelectionProvider>,
    );

    const marker = container.querySelector('.cluster-marker');
    expect(marker).not.toBeNull();
    expect(marker?.getAttribute('data-critical-members')).toBeNull();
    expect(marker?.getAttribute('data-critical-reasons')).toBeNull();
    expect(marker?.querySelector('.critical-ring')).toBeNull();
  });
});
