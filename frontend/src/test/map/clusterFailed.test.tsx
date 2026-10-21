import baselineFixture from '@contracts/fixtures/baseline.json';
import criticalityFixture from '@contracts/fixtures/criticality.json';
import networkFixture from '@contracts/fixtures/network.json';
import { fireEvent, render, screen } from '@testing-library/react';
import type { JSX } from 'react';
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

import {
  parseCriticalityResponse,
  parseNetworkResponse,
  parseScenarioReport,
} from '../../api/guards';
import type { NetworkResponse } from '../../api/types';
import { MapView } from '../../map/MapView';
import type { ElementRef } from '../../state/selectionContext';
import {
  isFailedIn,
  NOTHING_FAILED,
  withRestored,
  withToggled,
} from '../../state/failedSet';
import { FailureProvider } from '../../state/failures';
import { SelectionProvider } from '../../state/selection';

const criticality = parseCriticalityResponse(criticalityFixture);
const baseline = parseScenarioReport(baselineFixture);

/**
 * A cluster absorbs its members' glyphs, so a failed node inside one stops
 * looking failed unless the marker says otherwise.
 *
 * This is not hypothetical. On the real network seven of the 37 nodes sit in a
 * cluster at the default view, so a reader could fail one from the popover and
 * watch the map not change, which is precisely the feedback R11 exists to
 * give.
 *
 * The committed fixture does not cluster, so this moves one node onto another
 * to create the case. That is the only way to exercise it.
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

/**
 * A real provider rather than a stub, because the behaviour under test is that
 * toggling a member re-renders the marker. A stubbed value would never change
 * and the test would pass against a marker that cannot update.
 */
function Harness({ network }: { network: NetworkResponse }): JSX.Element {
  const [failed, setFailed] = useState(NOTHING_FAILED);
  const value = {
    failed,
    isFailed: (ref: ElementRef) => isFailedIn(failed, ref),
    toggle: (ref: ElementRef) => {
      setFailed((current) => withToggled(current, ref));
    },
    restore: (ref: ElementRef) => {
      setFailed((current) => withRestored(current, ref));
    },
    restoreAll: () => {
      setFailed(NOTHING_FAILED);
    },
  };
  return (
    <FailureProvider value={value}>
      <SelectionProvider>
        <MapView
          network={network}
          criticality={criticality}
          mostUtilized={baseline.most_utilized}
        />
      </SelectionProvider>
    </FailureProvider>
  );
}

function renderClustered(): HTMLElement {
  const { container } = render(<Harness network={coLocatedNetwork()} />);
  return container;
}

describe('a cluster containing a failed node', () => {
  it('is unmarked until one of its members is failed', () => {
    const container = renderClustered();
    const marker = container.querySelector('.cluster-marker');
    expect(marker).not.toBeNull();
    expect(marker?.getAttribute('data-failed')).toBeNull();
  });

  it('shows the failure once a member is failed from the popover', async () => {
    const container = renderClustered();

    const marker = container.querySelector('.cluster-marker');
    if (!(marker instanceof SVGElement)) throw new Error('no cluster marker rendered');
    fireEvent.mouseEnter(marker);

    // The popover lists both members; failing one must mark the whole cluster,
    // because the member's own glyph is not drawn while it is clustered.
    const entry = await screen.findByRole('menuitem', { name: /OPS-EAST-1/ });
    fireEvent.click(entry);

    const updated = container.querySelector('.cluster-marker');
    expect(updated?.getAttribute('data-failed')).toBe('true');
    expect(updated?.getAttribute('data-failed-members')).toBe('1');
    // D21: shape, not colour. The same cross a failed node carries.
    expect(updated?.querySelector('.failed-marker')).not.toBeNull();
    // A screen reader cannot see the cross, so the label has to say it too.
    expect(updated?.getAttribute('aria-label')).toContain('1 failed');
  });
});
