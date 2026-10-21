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
 * Critical and Top five utilized need data that is not ready on the very first render
 * (the criticality and baseline requests are still in flight), so both are optional here;
 * each panel shows its own placeholder until App has them, exactly as it did before P17.
 */
export function SidePanel({
  network,
  criticality,
  baseline,
}: {
  network: NetworkResponse | null;
  criticality: CriticalityResponse | null;
  baseline: ScenarioReport | null;
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
      {baseline === null || network === null ? (
        <section className="panel-section" aria-labelledby="top-utilized-heading">
          <h2 id="top-utilized-heading" className="panel-section-title">
            Top five utilized
          </h2>
          <p className="panel-empty">Loading the baseline scenario.</p>
        </section>
      ) : (
        <TopUtilizedPanel report={baseline} network={network} />
      )}
      <ImpactPanel />
    </aside>
  );
}
