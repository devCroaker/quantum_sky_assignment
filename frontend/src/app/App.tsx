import type { JSX } from 'react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import type { NetworkDataSource } from '../api';
import type { CriticalityResponse, NetworkResponse, ScenarioReport } from '../api/types';
import { MapView } from '../map/MapView';
import { SidePanel } from '../panels/SidePanel';
import type { FailureSet } from '../state/failedSet';
import {
  isFailedIn,
  NOTHING_FAILED,
  toScenarioRequest,
  withRestored,
  withToggled,
} from '../state/failedSet';
import type { FailureContextValue } from '../state/failureContext';
import { FailureProvider } from '../state/failures';
import { SelectionProvider } from '../state/selection';
import type { ElementRef } from '../state/selectionContext';

/**
 * The shell: map on the left at roughly two thirds, persistent side panel on the right at
 * one third. The split is decided by the panel and lives in App.css, not here.
 *
 * The network, the criticality assessment and the baseline are each loaded once and do not
 * depend on each other. The failed set is held here and nowhere else (R11): every change to
 * it posts the whole set to the scenario endpoint and keeps the answer. Restoring everything
 * is a request with two empty lists, not a special case. The baseline is the answer for the
 * empty set, so it is what is shown until the first change resolves.
 */
export function App({ source }: { source: NetworkDataSource }): JSX.Element {
  const [network, setNetwork] = useState<NetworkResponse | null>(null);
  const [criticality, setCriticality] = useState<CriticalityResponse | null>(null);
  const [baseline, setBaseline] = useState<ScenarioReport | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [failed, setFailed] = useState<FailureSet>(NOTHING_FAILED);
  // Mirrors `failed` synchronously. Two toggles in one tick must both see the first, and a
  // state read from a closure would only see whatever the last render committed.
  const failedRef = useRef<FailureSet>(NOTHING_FAILED);
  const [scenario, setScenario] = useState<ScenarioReport | null>(null);
  const [scenarioError, setScenarioError] = useState<string | null>(null);
  const [scenarioPending, setScenarioPending] = useState(false);
  // Each request takes the next number. A response is applied only if its number is still
  // the latest, so an older answer that arrives late cannot overwrite a newer one.
  const latestRequest = useRef(0);

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

  const applyFailed = useCallback(
    (next: FailureSet) => {
      failedRef.current = next;
      setFailed(next);
      latestRequest.current += 1;
      const requestNumber = latestRequest.current;
      setScenarioPending(true);
      source.scenario(toScenarioRequest(next)).then(
        (report) => {
          if (requestNumber !== latestRequest.current) return;
          setScenario(report);
          setScenarioError(null);
          setScenarioPending(false);
        },
        (reason: unknown) => {
          // A rejected request leaves the failed set as the user set it, so it can still be
          // restored. The report on screen stays the last one that resolved, and the Impact
          // panel says which set that one answers.
          if (requestNumber !== latestRequest.current) return;
          setScenarioError(reason instanceof Error ? reason.message : String(reason));
          setScenarioPending(false);
        },
      );
    },
    [source],
  );

  const toggle = useCallback(
    (ref: ElementRef) => {
      applyFailed(withToggled(failedRef.current, ref));
    },
    [applyFailed],
  );

  const restore = useCallback(
    (ref: ElementRef) => {
      applyFailed(withRestored(failedRef.current, ref));
    },
    [applyFailed],
  );

  const restoreAll = useCallback(() => {
    applyFailed(NOTHING_FAILED);
  }, [applyFailed]);

  const failure = useMemo<FailureContextValue>(
    () => ({
      failed,
      isFailed: (ref) => isFailedIn(failed, ref),
      toggle,
      restore,
      restoreAll,
    }),
    [failed, toggle, restore, restoreAll],
  );

  // What the panels show: the latest answer that resolved, or the baseline before any change.
  const report = scenario ?? baseline;

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
        <FailureProvider value={failure}>
          <SelectionProvider>
            {network === null ? (
              <section className="map" aria-labelledby="map-heading">
                <h2 id="map-heading">Map</h2>
              </section>
            ) : (
              <MapView
                network={network}
                criticality={criticality ?? undefined}
                mostUtilized={report?.most_utilized}
              />
            )}
            <SidePanel
              network={network}
              criticality={criticality}
              report={report}
              scenarioPending={scenarioPending}
              scenarioError={scenarioError}
            />
          </SelectionProvider>
        </FailureProvider>
      </main>
    </div>
  );
}
