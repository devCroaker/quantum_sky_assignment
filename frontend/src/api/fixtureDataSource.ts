import baselineFixture from '@contracts/fixtures/baseline.json';
import criticalityFixture from '@contracts/fixtures/criticality.json';
import networkFixture from '@contracts/fixtures/network.json';
import berlinDownFixture from '@contracts/fixtures/scenario-berlin-down.json';

import type { NetworkDataSource } from './dataSource';
import {
  parseCriticalityResponse,
  parseNetworkResponse,
  parseScenarioReport,
} from './guards';
import type { CriticalityResponse, ScenarioReport, ScenarioRequest } from './types';

/**
 * The fixture source, which is what runs today.
 *
 * contracts/fixtures/ holds four hand-worked payloads over a seven-node cut-down of the
 * network. Two of them are scenario reports, the baseline and Berlin failed, so the
 * fixture can answer exactly two scenario requests. Anything else is rejected with a
 * message that says so, rather than quietly returning the baseline and leaving a reviewer
 * to wonder why failing Hamburg changed nothing.
 *
 * The criticality payload covers all fifteen elements of that network, so the panels can
 * be built and reviewed in full before any endpoint exists.
 *
 * The fixtures go through the same guards as a live response. They are committed JSON and
 * could be trusted, but running them through the boundary means the guards are exercised
 * on every page load during development, which is where a mistake in them would show.
 */
export const BERLIN = 'Berlin';

function isBaselineRequest(request: ScenarioRequest): boolean {
  return (
    (request.failed_nodes ?? []).length === 0 && (request.failed_links ?? []).length === 0
  );
}

function isBerlinRequest(request: ScenarioRequest): boolean {
  const nodes = request.failed_nodes ?? [];
  return (
    nodes.length === 1 && nodes[0] === BERLIN && (request.failed_links ?? []).length === 0
  );
}

function describeRequest(request: ScenarioRequest): string {
  const nodes = request.failed_nodes ?? [];
  const links = request.failed_links ?? [];
  return `nodes [${nodes.join(', ')}], links [${links.join(', ')}]`;
}

export function createFixtureDataSource(): NetworkDataSource {
  return {
    label: 'fixture',

    network: () => Promise.resolve(parseNetworkResponse(networkFixture, 'network.json')),

    baseline: () =>
      Promise.resolve(parseScenarioReport(baselineFixture, 'baseline.json')),

    criticality: (): Promise<CriticalityResponse> =>
      Promise.resolve(parseCriticalityResponse(criticalityFixture, 'criticality.json')),

    scenario: (request: ScenarioRequest): Promise<ScenarioReport> => {
      if (isBaselineRequest(request)) {
        return Promise.resolve(parseScenarioReport(baselineFixture, 'baseline.json'));
      }
      if (isBerlinRequest(request)) {
        return Promise.resolve(
          parseScenarioReport(berlinDownFixture, 'scenario-berlin-down.json'),
        );
      }
      return Promise.reject(
        new Error(
          `that scenario is not available in fixture mode: ${describeRequest(request)}. ` +
            'The fixtures cover the empty failed set and the single node Berlin only. ' +
            'Run with VITE_DATA_SOURCE=live once P13 lands.',
        ),
      );
    },
  };
}
