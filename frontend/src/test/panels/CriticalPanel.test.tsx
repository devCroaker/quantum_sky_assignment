import criticalityFixture from '@contracts/fixtures/criticality.json';
import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { parseCriticalityResponse } from '../../api/guards';
import type { Assessment, CriticalityResponse } from '../../api/types';
import { CriticalPanel } from '../../panels/CriticalPanel';
import { matchesReasonFilter, DEFAULT_REASONS } from '../../panels/criticalFilter';
import { SelectionProvider } from '../../state/selection';

const fixture = parseCriticalityResponse(criticalityFixture);

function renderPanel(
  criticality: CriticalityResponse = fixture,
): ReturnType<typeof render> {
  return render(
    <SelectionProvider>
      <CriticalPanel criticality={criticality} />
    </SelectionProvider>,
  );
}

function assessment(
  id: string,
  kind: 'node' | 'link',
  reasons: Assessment['reasons'],
): Assessment {
  return {
    id,
    kind,
    critical: (reasons ?? []).length > 0,
    reasons,
    impact: {
      components: 1,
      endpoint_affected_demands: 0,
      endpoint_affected_units: 0,
      max_utilization: 0,
      overloaded_links: 0,
      undeliverable_demands: 0,
      undeliverable_units: 0,
    },
  };
}

describe('CriticalPanel', () => {
  it('shows the fixture-derived headline counts (3 of 7 nodes, 3 of 8 links)', () => {
    renderPanel();
    expect(screen.getByText(/3 of 7 nodes/)).toBeTruthy();
    expect(screen.getByText(/3 of 8 links/)).toBeTruthy();
  });

  it('shows a per-reason count derived from the assessments, not hardcoded', () => {
    renderPanel();
    // Counted by hand from contracts/fixtures/criticality.json: partitions-network and
    // demands-undeliverable each apply to ACC-HUB-EAST-Warsaw, ACC-OPS-EAST-1-HUB-EAST,
    // L4, Berlin, HUB-EAST and Warsaw (6); links-overloaded applies to none (0).
    expect(screen.getByText(/Partitions the network \(6\)/)).toBeTruthy();
    expect(screen.getByText(/Leaves a demand undeliverable \(6\)/)).toBeTruthy();
    expect(screen.getByText(/Overloads a surviving link \(0\)/)).toBeTruthy();
  });

  it('defaults to the structural reasons, naming the exact three nodes an operations lead wants', () => {
    const { container } = renderPanel();
    const ids = Array.from(container.querySelectorAll('.critical-row-id')).map(
      (el) => el.textContent,
    );
    // Every critical element: the three nodes whose loss partitions the network or
    // strands a demand elsewhere, and the three links with the same reasons. DC-NORTH,
    // Hamburg and OPS-EAST-1 lose only their own traffic, so under D24 they are not
    // critical at all and cannot appear whatever the filter says.
    expect(ids.sort()).toEqual(
      [
        'ACC-HUB-EAST-Warsaw',
        'ACC-OPS-EAST-1-HUB-EAST',
        'Berlin',
        'HUB-EAST',
        'L4',
        'Warsaw',
      ].sort(),
    );
    // 6 critical elements in total, 3 nodes and 3 links, matching the fixture's own
    // summary. Every reason is on by default now that each one describes harm to
    // somebody else, so the default view hides nothing.
    expect(screen.getByText('Showing 6 of 6 critical elements')).toBeTruthy();
  });

  it('shows a node matching any selected reason, not only one matching all of them', () => {
    // The filter is an OR over the selected reasons, and this fabricates the case that
    // tells that apart from an AND. A node carrying one selected reason must show even
    // when it lacks the others; only a node carrying none of them is hidden. The
    // committed fixture cannot distinguish the two readings, because every critical
    // element in it carries both structural reasons, so the case is built by hand.
    const fabricated: CriticalityResponse = {
      assessments: [
        assessment('PartitionsOnly', 'node', ['partitions-network']),
        assessment('OverloadsOnly', 'node', ['links-overloaded']),
        assessment('Both', 'node', ['partitions-network', 'links-overloaded']),
        assessment('NotCritical', 'node', []),
      ],
      summary: {
        critical_links: 0,
        critical_nodes: 3,
        links_evaluated: 0,
        nodes_evaluated: 4,
      },
    };
    const { container } = renderPanel(fabricated);
    const ids = Array.from(container.querySelectorAll('.critical-row-id')).map(
      (el) => el.textContent,
    );
    expect(ids.sort()).toEqual(['Both', 'OverloadsOnly', 'PartitionsOnly'].sort());
    expect(ids).not.toContain('NotCritical');
  });

  it('matchesReasonFilter is inclusive (OR over reasons), the property the UI relies on', () => {
    const partitionsOnly = assessment('x', 'node', ['partitions-network']);
    const notCritical = assessment('y', 'node', []);
    expect(matchesReasonFilter(partitionsOnly, DEFAULT_REASONS)).toBe(true);
    expect(
      matchesReasonFilter(partitionsOnly, new Set(['links-overloaded'] as const)),
    ).toBe(false);
    expect(matchesReasonFilter(notCritical, DEFAULT_REASONS)).toBe(false);
  });

  it('narrows the list only when every reason an element carries is cleared', () => {
    renderPanel();
    expect(screen.getByText('Showing 6 of 6 critical elements')).toBeTruthy();

    // Every critical element in this fixture carries BOTH structural reasons, so
    // clearing one changes nothing. That is worth asserting rather than assuming,
    // because it is the inclusive filter behaving correctly: an element shows while
    // any selected reason still matches.
    screen.getByLabelText(/Partitions the network/).click();
    expect(screen.getByText('Showing 6 of 6 critical elements')).toBeTruthy();
    within(screen.getByRole('list')).getByText('Warsaw');

    // Clearing the second one empties the list, since nothing in this network
    // overloads a link.
    screen.getByLabelText(/Leaves a demand undeliverable/).click();
    expect(screen.getByText('Showing 0 of 6 critical elements')).toBeTruthy();
  });
});
