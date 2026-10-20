import type { NetworkDataSource } from './dataSource';
import {
  parseCriticalityResponse,
  parseNetworkResponse,
  parseScenarioReport,
} from './guards';
import type { CriticalityResponse, ScenarioReport, ScenarioRequest } from './types';

/**
 * The live source, against the four endpoints in docs/api-contract.md.
 *
 * Paths are relative, so the browser sends them to its own origin and the Vite proxy
 * forwards /api to the back end. Nothing here knows the back end's host or port, which
 * keeps the deployed build and the development build identical.
 */
const PREFIX = '/api/v1';

/** The back end reports a rejected request as an ErrorResponse, per the contract. */
async function readErrorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (typeof body === 'object' && body !== null && 'error' in body) {
      const detail: unknown = body.error;
      if (typeof detail === 'object' && detail !== null && 'message' in detail) {
        const message: unknown = detail.message;
        if (typeof message === 'string') return message;
      }
    }
  } catch {
    // A non-JSON body is not worth a second failure mode. Fall through to the status.
  }
  return response.statusText;
}

async function request(path: string, init?: RequestInit): Promise<unknown> {
  const response = await fetch(`${PREFIX}${path}`, init);
  if (!response.ok) {
    throw new Error(
      `${init?.method ?? 'GET'} ${PREFIX}${path} failed with ${String(response.status)}: ` +
        (await readErrorMessage(response)),
    );
  }
  return response.json();
}

export function createLiveDataSource(): NetworkDataSource {
  return {
    label: 'live',

    network: async () => parseNetworkResponse(await request('/network')),

    baseline: async () => parseScenarioReport(await request('/analysis/baseline')),

    criticality: async (): Promise<CriticalityResponse> =>
      parseCriticalityResponse(await request('/criticality')),

    scenario: async (scenario: ScenarioRequest): Promise<ScenarioReport> =>
      parseScenarioReport(
        await request('/scenario', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(scenario),
        }),
      ),
  };
}
