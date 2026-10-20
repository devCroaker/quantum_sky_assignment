import networkFixture from '@contracts/fixtures/network.json';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { parseNetworkResponse } from '../../api/guards';
import type { NetworkResponse, NodeWire } from '../../api/types';
import { MapView } from '../../map/MapView';

const fixture = parseNetworkResponse(networkFixture);

describe('MapView', () => {
  // The committed fixture (contracts/fixtures/network.json) is a seven-node cut-down of
  // the real network with eight links, not the real 37/55: asserting against the
  // fixture's own counts means this test stays correct once the view switches to the
  // full network at P13, instead of silently checking the wrong number forever.
  it('renders every node and every link in the fixture', () => {
    const { container } = render(<MapView network={fixture} />);
    expect(container.querySelectorAll('.node-glyph')).toHaveLength(fixture.nodes.length);
    expect(container.querySelectorAll('.link')).toHaveLength(fixture.links.length);
  });

  it('gives every node kind in the fixture its own, non-colour shape (D21)', () => {
    const { container } = render(<MapView network={fixture} />);
    const shapeByKind = new Map<string, string>();
    for (const node of fixture.nodes) {
      const glyph = container.querySelector(`[data-node-id="${node.id}"]`);
      const shape = glyph?.getAttribute('data-shape');
      expect(shape).toBeTruthy();
      const recorded = shapeByKind.get(node.kind);
      if (recorded === undefined) {
        shapeByKind.set(node.kind, shape as string);
      } else {
        // Same kind seen twice: it had better still claim the same shape.
        expect(shape).toBe(recorded);
      }
    }
    // And different kinds must not collide on the same shape, or the "non-colour"
    // channel D21 asks for would carry no information.
    expect(new Set(shapeByKind.values()).size).toBe(shapeByKind.size);
  });
});

/**
 * A network with two nodes forced to the same position, which clusterByProximity will
 * always group regardless of the current zoom (distance zero is inside any threshold).
 * clustering.test.ts already proves the threshold arithmetic in isolation; this fixture
 * exists to drive the popover end to end through a real MapView render.
 */
function networkWithCluster(): NetworkResponse {
  const clusterA: NodeWire = {
    id: 'CLUSTER-DC',
    kind: 'data-center',
    position: { x: 10, y: 50 },
    can_transit: false,
    attaches_to: ['Hamburg'],
  };
  const clusterB: NodeWire = {
    id: 'CLUSTER-OPS',
    kind: 'operations-site',
    position: { x: 10, y: 50 },
    can_transit: false,
    attaches_to: [],
  };
  return { ...fixture, nodes: [...fixture.nodes, clusterA, clusterB] };
}

function openPopover(): { marker: Element; menu: HTMLElement } {
  const { container } = render(<MapView network={networkWithCluster()} />);
  const marker = container.querySelector('.cluster-marker');
  expect(marker).not.toBeNull();
  if (marker === null) throw new Error('unreachable, asserted above');
  fireEvent.focus(marker);
  const menu = screen.getByRole('menu');
  return { marker, menu };
}

describe('MapView cluster popover', () => {
  it('shows a visible count on the cluster marker before it is ever opened', () => {
    const { container } = render(<MapView network={networkWithCluster()} />);
    const marker = container.querySelector('.cluster-marker');
    // Text, not colour: a reader sees "2" without hovering anything (D21 applied to the
    // marker itself, not only to the glyphs).
    expect(marker?.textContent).toContain('2');
  });

  it('opens on focus and lists every member as a real, labelled button', () => {
    const { menu } = openPopover();
    const items = within(menu).getAllByRole('menuitem');
    expect(items).toHaveLength(2);
    for (const item of items) {
      expect(item.tagName).toBe('BUTTON');
    }
    // getByText throws if the text is missing, which is the assertion: each call only
    // needs to resolve, not be wrapped in another expect.
    within(menu).getByText('CLUSTER-DC');
    within(menu).getByText('CLUSTER-OPS');
    within(menu).getByText('data center');
    within(menu).getByText('operations site');
    // "near what it attaches to" (R9) made legible in the popover: only the member that
    // has an attachment shows one.
    within(menu).getByText(/attaches to Hamburg/);
  });

  it('closes on Escape and hands focus back to the marker', () => {
    const { marker, menu } = openPopover();

    fireEvent.keyDown(menu, { key: 'Escape' });

    expect(screen.queryByRole('menu')).toBeNull();
    expect(document.activeElement).toBe(marker);
  });

  it('moves focus between entries with arrow keys, wrapping at the ends', () => {
    const { menu } = openPopover();
    const [first, second] = within(menu).getAllByRole('menuitem');
    expect(first).toBeDefined();
    expect(second).toBeDefined();

    // The effect that focuses the first entry on open has already run.
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(menu, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(second);

    fireEvent.keyDown(menu, { key: 'ArrowDown' });
    expect(document.activeElement).toBe(first);

    fireEvent.keyDown(menu, { key: 'ArrowUp' });
    expect(document.activeElement).toBe(second);
  });
});
