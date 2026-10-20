import type { JSX } from 'react';

import { PanelSection } from './PanelSection';

/**
 * The impact of the current failure. Filled by P18, answering R8 and R11.
 *
 * P18 owns the failed set, posts it to /api/v1/scenario, and renders the report here:
 * partitioned or not, the undeliverable demands, and separately the demands affected only
 * because their own endpoint is gone. The section is present and empty rather than absent
 * so that failing an element does not change the shape of the layout.
 */
export function ImpactPanel(): JSX.Element {
  return (
    <PanelSection
      id="impact"
      title="Impact"
      lands="P18 fills this from POST /api/v1/scenario, for R8 and R11."
    >
      <p className="panel-empty">Nothing failed. Select an element once P18 lands.</p>
    </PanelSection>
  );
}
