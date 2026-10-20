import { describe, expect, it } from 'vitest';

import { createFixtureDataSource } from '../api/fixtureDataSource';

const source = createFixtureDataSource();

describe('the fixture data source', () => {
  it('serves the network fixture with its own totals', async () => {
    const network = await source.network();
    // contracts/fixtures/network.json is the seven-node cut-down described in
    // docs/api-contract.md, not the real network. The R1 figures of 37 and 55 are
    // asserted against the real loaders in P7, not here.
    expect(network.totals.nodes).toBe(7);
    expect(network.totals.links).toBe(8);
    expect(network.nodes).toHaveLength(7);
    expect(network.links).toHaveLength(8);
  });

  it('returns the baseline for an empty failed set', async () => {
    const report = await source.scenario({});
    expect(report.failed.nodes).toEqual([]);
    expect(report.failed.links).toEqual([]);
    expect(report.partitioned).toBe(false);
    // The baseline and an empty scenario request are the same payload, per the contract.
    expect(report).toEqual(await source.baseline());
  });

  it('treats explicitly empty arrays as the baseline too', async () => {
    const report = await source.scenario({ failed_nodes: [], failed_links: [] });
    expect(report).toEqual(await source.baseline());
  });

  it('returns the Berlin report when exactly Berlin fails', async () => {
    const report = await source.scenario({ failed_nodes: ['Berlin'] });
    expect(report.failed.nodes).toEqual(['Berlin']);
    expect(report.partitioned).toBe(true);
    expect(report.components).toBe(2);
    expect(report.undeliverable_demands.map((demand) => demand.id)).toEqual(['D1', 'D2']);
  });

  it.each([
    { name: 'another node', request: { failed_nodes: ['Hamburg'] } },
    {
      name: 'Berlin plus another node',
      request: { failed_nodes: ['Berlin', 'Hamburg'] },
    },
    { name: 'a link', request: { failed_links: ['L2'] } },
    {
      name: 'Berlin plus a link',
      request: { failed_nodes: ['Berlin'], failed_links: ['L2'] },
    },
  ])('rejects $name, naming fixture mode', async ({ request }) => {
    await expect(source.scenario(request)).rejects.toThrow(
      /not available in fixture mode/,
    );
  });

  it('rejects criticality, which has no committed fixture', async () => {
    await expect(source.criticality()).rejects.toThrow(/not available in fixture mode/);
  });
});
