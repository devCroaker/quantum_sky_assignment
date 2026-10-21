import type { JSX } from 'react';

import type { CriticalityResponse, NetworkResponse, ScenarioReport } from '../api/types';
import { CriticalPanel } from './CriticalPanel';
import { ImpactPanel } from './ImpactPanel';
import { TopUtilizedPanel } from './TopUtilizedPanel';

/**
 * The side panel, persistent by decision of the panel.
 *
 * It is always mounted and always in the same place, in this order: Critical, Top five
 * utilized, Impact. Nothing collapses or appears on selection, so the operations lead
 * reads the same three answers in the same spots whether or not anything is down.
 *
 * Critical depends only on the criticality assessment, which is for the network as built.
 * Top five utilized and Impact follow `report`, the latest scenario answer, so they move
 * when an element is failed or restored. Each shows its own placeholder until its data
 * arrives.
 */
export function SidePanel({
  network,
  criticality,
  report,
  scenarioPending,
  scenarioError,
}: {
  network: NetworkResponse | null;
  criticality: CriticalityResponse | null;
  report: ScenarioReport | null;
  scenarioPending: boolean;
  scenarioError: string | null;
}): JSX.Element {
  return (
    <aside className="side-panel" aria-label="Analysis">
      {criticality === null ? (
        <section className="panel-section" aria-labelledby="critical-heading">
          <h2 id="critical-heading" className="panel-section-title">
            Critical
          </h2>
          <p className="panel-empty">Loading the criticality assessment.</p>
        </section>
      ) : (
        <CriticalPanel criticality={criticality} />
      )}
      {report === null || network === null ? (
        <section className="panel-section" aria-labelledby="top-utilized-heading">
          <h2 id="top-utilized-heading" className="panel-section-title">
            Top five utilized
          </h2>
          <p className="panel-empty">Loading the baseline scenario.</p>
        </section>
      ) : (
        <TopUtilizedPanel report={report} network={network} />
      )}
      <ImpactPanel report={report} pending={scenarioPending} error={scenarioError} />
    </aside>
  );
}
