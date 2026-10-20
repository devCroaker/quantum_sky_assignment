import type { JSX } from 'react';

import { PanelSection } from './PanelSection';

/**
 * The five most utilized links. Filled by P17, answering R10.
 *
 * The ordering is not recomputed here. ScenarioReport.most_utilized already carries the
 * five links with their server-side rank, including how ties were broken, so the view
 * cannot disagree with the API about which five they are.
 */
export function TopUtilizedPanel(): JSX.Element {
  return (
    <PanelSection
      id="top-utilized"
      title="Top five utilized"
      lands="P17 fills this from ScenarioReport.most_utilized, for R10."
    >
      <p className="panel-empty">No scenario loaded yet.</p>
    </PanelSection>
  );
}
