import { render, screen } from '@testing-library/react';
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

  it('makes every placeholder element that P18 will click keyboard reachable', async () => {
    render(<App source={createFixtureDataSource()} />);

    const chips = await screen.findAllByRole('button');
    expect(chips).toHaveLength(7);
    // Real buttons, none of them disabled, so the tab order already reaches all seven.
    for (const chip of chips) {
      expect(chip.tagName).toBe('BUTTON');
      expect(chip.hasAttribute('disabled')).toBe(false);
    }
  });
});
