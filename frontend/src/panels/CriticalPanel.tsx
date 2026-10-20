import type { JSX } from 'react';

import { PanelSection } from './PanelSection';

/**
 * Critical elements. Filled by P17, answering R10.
 *
 * P17 reads CriticalityResponse, keeps the assessments whose reason list is non-empty,
 * and lists them with the reason spelled out in words. R10 says not by colour alone, so
 * the reason text and an icon carry the meaning and colour only reinforces it.
 */
export function CriticalPanel(): JSX.Element {
  return (
    <PanelSection
      id="critical"
      title="Critical"
      lands="P17 fills this from GET /api/v1/criticality, for R10."
    >
      <p className="panel-empty">No assessment loaded yet.</p>
    </PanelSection>
  );
}
