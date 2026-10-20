import type {
  CriticalityResponse,
  NetworkResponse,
  ScenarioReport,
  ScenarioRequest,
} from './types';

/**
 * The only way the view reaches data.
 *
 * There are two implementations, one over the committed fixtures and one over the live
 * API, and no view code knows which it has. That is what lets the front end lane finish
 * the map and the panels before the endpoints exist, and then switch over by changing an
 * environment variable rather than by editing a component.
 *
 * The methods mirror the four endpoints in docs/api-contract.md one for one. There is no
 * caching and no state here: the API is a pure function of the request, per D5.
 */
export interface NetworkDataSource {
  /** The name shown in the header, so it is obvious which source is in play. */
  readonly label: string;
  network(): Promise<NetworkResponse>;
  baseline(): Promise<ScenarioReport>;
  criticality(): Promise<CriticalityResponse>;
  scenario(request: ScenarioRequest): Promise<ScenarioReport>;
}

export type DataSourceName = 'fixture' | 'live';

/**
 * Read the selected source from the environment.
 *
 * Defaults to the fixture, because that is the mode that works with no back end running,
 * and an unset variable should leave the application usable rather than broken.
 */
export function resolveDataSourceName(raw: string | undefined): DataSourceName {
  if (raw === undefined || raw === '') return 'fixture';
  if (raw === 'fixture' || raw === 'live') return raw;
  throw new Error(
    `VITE_DATA_SOURCE must be "fixture" or "live", got ${JSON.stringify(raw)}`,
  );
}
