import type { JSX } from 'react';
import { useEffect, useState } from 'react';

import type { NetworkDataSource } from '../api';
import { MapView } from '../map/MapView';
import { SidePanel } from '../panels/SidePanel';
import { SelectionProvider } from '../state/selection';
import type { CriticalityResponse, NetworkResponse, ScenarioReport } from '../api/types';

/**
 * The shell: map on the left at roughly two thirds, persistent side panel on the right at
 * one third. The split is decided by the panel and lives in App.css, not here.
 *
 * The network, the criticality assessment and the baseline scenario are each loaded once
 * and do not depend on each other, so they are three independent effects rather than a
 * waterfall: the map can draw its topology before the criticality overlay (R10) or the top
 * five list (R10) resolve, and each side panel section shows its own placeholder until its
 * own data arrives (see SidePanel). P18 adds the failed set and the scenario request on top
 * of this; it will own that state, which is why the load here is deliberately the simplest
 * thing that works rather than a general cache.
 */
export function App({ source }: { source: NetworkDataSource }): JSX.Element {
  const [network, setNetwork] = useState<NetworkResponse | null>(null);
  const [criticality, setCriticality] = useState<CriticalityResponse | null>(null);
  const [baseline, setBaseline] = useState<ScenarioReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    source
      .network()
      .then((response) => {
        if (live) setNetwork(response);
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      live = false;
    };
  }, [source]);

  useEffect(() => {
    let live = true;
    source
      .criticality()
      .then((response) => {
        if (live) setCriticality(response);
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      live = false;
    };
  }, [source]);

  useEffect(() => {
    let live = true;
    source
      .baseline()
      .then((response) => {
        if (live) setBaseline(response);
      })
      .catch((reason: unknown) => {
        if (live) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      live = false;
    };
  }, [source]);

  return (
    <div className="app">
      <header className="app-header">
        <h1>netscope</h1>
        {/*
          The R1 acceptance figures, on screen because seeing 37 nodes and 55 links while
          developing is the cheapest check that the right data arrived. The fixture is a
          seven-node cut-down, so these read 7 and 8 until the live source is switched on.
        */}
        {network === null ? (
          <p className="totals" role="status">
            {error === null
              ? 'Loading the network'
              : `Could not load the network: ${error}`}
          </p>
        ) : (
          <dl className="totals">
            <div>
              <dt>Nodes</dt>
              <dd>{network.totals.nodes}</dd>
            </div>
            <div>
              <dt>Links</dt>
              <dd>{network.totals.links}</dd>
            </div>
            <div>
              <dt>Demands</dt>
              <dd>{network.totals.demands}</dd>
            </div>
            <div>
              <dt>Demand units</dt>
              <dd>{network.totals.demand_units}</dd>
            </div>
          </dl>
        )}
        <p className="source-badge">source: {source.label}</p>
      </header>

      <main className="app-body">
        <SelectionProvider>
          {network === null ? (
            <section className="map" aria-labelledby="map-heading">
              <h2 id="map-heading">Map</h2>
            </section>
          ) : (
            <MapView
              network={network}
              criticality={criticality ?? undefined}
              mostUtilized={baseline?.most_utilized}
            />
          )}
          <SidePanel network={network} criticality={criticality} baseline={baseline} />
        </SelectionProvider>
      </main>
    </div>
  );
}
