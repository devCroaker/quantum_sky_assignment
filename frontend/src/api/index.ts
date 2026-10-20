import type { DataSourceName, NetworkDataSource } from './dataSource';
import { resolveDataSourceName } from './dataSource';
import { createFixtureDataSource } from './fixtureDataSource';
import { createLiveDataSource } from './liveDataSource';

export type { NetworkDataSource, DataSourceName } from './dataSource';
export { resolveDataSourceName } from './dataSource';
export { WireFormatError } from './guards';

export function createDataSource(name: DataSourceName): NetworkDataSource {
  return name === 'live' ? createLiveDataSource() : createFixtureDataSource();
}

/**
 * The source the application actually uses, chosen once at module load.
 *
 * VITE_DATA_SOURCE is read here and nowhere else, so there is exactly one place that
 * decides, and a test can build either source directly without touching the environment.
 */
export const dataSource: NetworkDataSource = createDataSource(
  resolveDataSourceName(import.meta.env.VITE_DATA_SOURCE),
);
