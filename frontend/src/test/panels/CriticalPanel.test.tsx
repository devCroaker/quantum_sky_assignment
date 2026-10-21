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
  it('shows the fixture-derived headline counts (6 of 7 nodes, 3 of 8 links)', () => {
    renderPanel();
    expect(screen.getByText(/6 of 7 nodes/)).toBeTruthy();
    expect(screen.getByText(/3 of 8 links/)).toBeTruthy();
  });

  it('shows a per-reason count derived from the assessments, not hardcoded', () => {
    renderPanel();
    // Counted by hand from contracts/fixtures/criticality.json: partitions-network and
    // demands-undeliverable each apply to ACC-HUB-EAST-Warsaw, ACC-OPS-EAST-1-HUB-EAST,
    // L4, Berlin, HUB-EAST and Warsaw (6); endpoint-demands-lost applies to DC-NORTH,
    // Hamburg, OPS-EAST-1 and Warsaw (4); links-overloaded applies to none (0).
    expect(screen.getByText(/Partitions the network \(6\)/)).toBeTruthy();
    expect(screen.getByText(/Leaves a demand undeliverable \(6\)/)).toBeTruthy();
    expect(screen.getByText(/Only loses its own traffic \(4\)/)).toBeTruthy();
    expect(screen.getByText(/Overloads a surviving link \(0\)/)).toBeTruthy();
  });

  it('defaults to the structural reasons, naming the exact three nodes an operations lead wants', () => {
    const { container } = renderPanel();
    const ids = Array.from(container.querySelectorAll('.critical-row-id')).map(
      (el) => el.textContent,
    );
    // Exactly the structural nodes and links: the three nodes whose loss partitions the
    // network or strands a demand, and the three links with the same reasons. DC-NORTH,
    // Hamburg and OPS-EAST-1 (critical only via endpoint-demands-lost) must NOT appear.
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
    // 9 total critical elements (6 nodes + 3 links, matching the fixture's own summary),
    // 6 of them structural.
    expect(screen.getByText('Showing 6 of 9 critical elements')).toBeTruthy();
  });

  it('keeps a node that is both structural and endpoint-affected under the default filter', () => {
    // This is the case that tells the correct (inclusive, OR-over-reasons) filter apart
    // from the wrong one an earlier draft used (subtract out endpoint-demands-lost). A
    // node that carries partitions-network ALONGSIDE endpoint-demands-lost, like Warsaw in
    // the real network's Athens/Dublin/Warsaw, must still show under the default view: the
    // wrong reading would drop it the moment it also happens to originate traffic, which
    // is backwards. The committed 15-element fixture's own Warsaw already covers exactly
    // this (see the test above); this fabricates a minimal case so the distinction cannot
    // be missed by an implementation that coincidentally passes the fixture-based test.
    const fabricated: CriticalityResponse = {
      assessments: [
        assessment('OnlyStructural', 'node', ['partitions-network']),
        assessment('StructuralAndEndpoint', 'node', [
          'partitions-network',
          'endpoint-demands-lost',
        ]),
        assessment('OnlyEndpoint', 'node', ['endpoint-demands-lost']),
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
    expect(ids.sort()).toEqual(['OnlyStructural', 'StructuralAndEndpoint'].sort());
    expect(ids).not.toContain('OnlyEndpoint');
  });

  it('matchesReasonFilter is inclusive (OR over reasons), the property the UI relies on', () => {
    const structuralAndEndpoint = assessment('x', 'node', [
      'partitions-network',
      'endpoint-demands-lost',
    ]);
    const onlyEndpoint = assessment('y', 'node', ['endpoint-demands-lost']);
    expect(matchesReasonFilter(structuralAndEndpoint, DEFAULT_REASONS)).toBe(true);
    expect(matchesReasonFilter(onlyEndpoint, DEFAULT_REASONS)).toBe(false);
  });

  it('changes the filtered list and its count when a reason checkbox is toggled', () => {
    renderPanel();
    expect(screen.getByText('Showing 6 of 9 critical elements')).toBeTruthy();

    const endpointCheckbox = screen.getByLabelText(/Only loses its own traffic/);
    endpointCheckbox.click();

    expect(screen.getByText('Showing 9 of 9 critical elements')).toBeTruthy();
    // Now visible: the three endpoint-only critical elements that were hidden by default.
    const list = screen.getByRole('list');
    within(list).getByText('DC-NORTH');
    within(list).getByText('Hamburg');
    within(list).getByText('OPS-EAST-1');
  });
});
