import baselineFixture from '@contracts/fixtures/baseline.json';
import networkFixture from '@contracts/fixtures/network.json';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { parseNetworkResponse, parseScenarioReport } from '../../api/guards';
import type { ScenarioReport } from '../../api/types';
import { TopUtilizedPanel } from '../../panels/TopUtilizedPanel';
import { SelectionProvider } from '../../state/selection';

const network = parseNetworkResponse(networkFixture);
const baseline = parseScenarioReport(baselineFixture);

function renderPanel(report: ScenarioReport = baseline): ReturnType<typeof render> {
  return render(
    <SelectionProvider>
      <TopUtilizedPanel report={report} network={network} />
    </SelectionProvider>,
  );
}

describe('TopUtilizedPanel', () => {
  it('lists the five links in the exact server order, never resorted', () => {
    const { container } = renderPanel();
    const rows = Array.from(container.querySelectorAll('tbody tr'));
    expect(rows).toHaveLength(5);
    // docs/api-contract.md decision 4: server order is rank ascending, which for this
    // fixture is ACC-OPS-EAST-1-HUB-EAST, L4, L2, ACC-HUB-EAST-Warsaw,
    // ACC-DC-NORTH-Copenhagen. Reading the DOM row order checks the view did not re-sort.
    const linkIdsInOrder = rows.map((row) => row.children[1]?.textContent);
    expect(linkIdsInOrder).toEqual(
      baseline.most_utilized.map((ranked) => ranked.link_id),
    );
    const ranksInOrder = rows.map((row) => row.getAttribute('data-rank'));
    expect(ranksInOrder).toEqual(['1', '2', '3', '4', '5']);
  });

  it('shows each row endpoints looked up from the network, not invented', () => {
    renderPanel();
    // Rank 1 is ACC-OPS-EAST-1-HUB-EAST, whose endpoints in network.json are HUB-EAST and
    // OPS-EAST-1.
    expect(screen.getByText(/HUB-EAST.*OPS-EAST-1/)).toBeTruthy();
  });

  it('shows utilization exactly as the payload gives it, never recomputed from load/capacity', () => {
    // ACC-HUB-EAST-Warsaw genuinely is load 10 over capacity 80 (12.5%), but this report is
    // fabricated with a utilization field that disagrees with that division on purpose. If
    // the view divided load by capacity itself, as docs/api-contract.md's conventions
    // would make tempting, it would show 12.5% instead of the given, deliberately wrong,
    // 99.9%. Showing 99.9% is this test passing.
    const fabricated: ScenarioReport = {
      ...baseline,
      most_utilized: [
        {
          link_id: 'ACC-HUB-EAST-Warsaw',
          load: 10,
          capacity: 80,
          utilization: 0.999,
          rank: 1,
        },
      ],
    };
    renderPanel(fabricated);
    expect(screen.getByText('99.9%')).toBeTruthy();
    expect(screen.queryByText('12.5%')).toBeNull();
  });

  it('shows a placeholder rather than a table when nothing carries load', () => {
    const empty: ScenarioReport = { ...baseline, most_utilized: [] };
    renderPanel(empty);
    expect(screen.getByText(/No links carry any load/)).toBeTruthy();
    expect(screen.queryByRole('table')).toBeNull();
  });
});
