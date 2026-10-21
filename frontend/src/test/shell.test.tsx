import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { createFixtureDataSource } from '../api/fixtureDataSource';
import { App } from '../app/App';

describe('the shell', () => {
  it('renders the three panel sections, in the order the panel settled on', async () => {
    render(<App source={createFixtureDataSource()} />);

    const headings = await screen.findAllByRole('heading', { level: 2 });
    expect(headings.map((heading) => heading.textContent)).toEqual([
      'Map',
      'Critical',
      'Top five utilized',
      'Impact',
    ]);
  });

  it('shows the totals from the fixture', async () => {
    render(<App source={createFixtureDataSource()} />);

    // The seven-node cut-down in contracts/fixtures/network.json. The real figures, 37
    // nodes and 55 links, appear in the same place once the live source is switched on.
    const nodes = await screen.findByText('Nodes');
    expect(nodes.parentElement?.textContent).toBe('Nodes7');
    expect(screen.getByText('Links').parentElement?.textContent).toBe('Links8');
    expect(screen.getByText('Demands').parentElement?.textContent).toBe('Demands2');
    expect(screen.getByText('Demand units').parentElement?.textContent).toBe(
      'Demand units110',
    );
  });

  it('makes every node on the map keyboard reachable, for P18 to build selection on', async () => {
    render(<App source={createFixtureDataSource()} />);

    // P16 replaced the node-chip placeholder with the real map: seven SVG node glyphs
    // (role="button", focusable), one per fixture node. P18 made each link a focusable
    // button too, so the glyphs are picked out by their data-node-id rather than counting
    // every button in the map. Scoped to the map's own <svg>, since the panels add buttons
    // of their own that this test is not about.
    const mapSvg = await screen.findByRole('application');
    const glyphs = within(mapSvg)
      .getAllByRole('button')
      .filter((element) => element.hasAttribute('data-node-id'));
    expect(glyphs).toHaveLength(7);
    for (const glyph of glyphs) {
      expect(glyph.getAttribute('tabindex')).toBe('0');
      expect(glyph.hasAttribute('aria-disabled')).toBe(false);
    }
  });
});
