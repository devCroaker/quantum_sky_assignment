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

  it('returns the criticality fixture for all fifteen elements', async () => {
    const report = await source.criticality();
    expect(report.assessments).toHaveLength(15);
    expect(report.summary.nodes_evaluated).toBe(7);
    expect(report.summary.links_evaluated).toBe(8);
  });

  it('reports three critical nodes and three critical links', async () => {
    // Three of seven: only the elements whose loss costs somebody else
    // something. The other four nodes either cost nothing at all or cost only
    // their own traffic, which R8 still reports and R7 no longer counts (D24).
    const report = await source.criticality();
    expect(report.summary.critical_nodes).toBe(3);
    expect(report.summary.critical_links).toBe(3);
    const safeNodes = report.assessments
      .filter((a) => a.kind === 'node' && !a.critical)
      .map((a) => a.id)
      .sort();
    // Copenhagen costs nothing when lost. The other three cost only their own
    // traffic, which is reported but is not a reason.
    expect(safeNodes).toEqual(['Copenhagen', 'DC-NORTH', 'Hamburg', 'OPS-EAST-1']);
  });

  it('reports traffic lost to a failed endpoint without calling it critical', async () => {
    // The distinction the revert in D24 turned on. These three strand a demand
    // when they fail, but only their own, so nothing that survives is worse off.
    // R8 still requires the units be reported, which is why the impact figures
    // are checked here as well as the empty reasons.
    const report = await source.criticality();
    const byId = new Map(
      report.assessments.filter((a) => a.kind === 'node').map((a) => [a.id, a]),
    );
    for (const id of ['DC-NORTH', 'Hamburg', 'OPS-EAST-1']) {
      const assessment = byId.get(id);
      expect(assessment?.reasons ?? []).toEqual([]);
      expect(assessment?.critical).toBe(false);
      expect(assessment?.impact.endpoint_affected_demands).toBe(1);
    }
  });
});
