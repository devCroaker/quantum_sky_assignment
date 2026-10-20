import type { JSX } from 'react';

import { CriticalPanel } from './CriticalPanel';
import { ImpactPanel } from './ImpactPanel';
import { TopUtilizedPanel } from './TopUtilizedPanel';

/**
 * The side panel, persistent by decision of the panel.
 *
 * It is always mounted and always in the same place, in this order: Critical, Top five
 * utilized, Impact. Nothing collapses or appears on selection, so the operations lead
 * reads the same three answers in the same spots whether or not anything is down.
 */
export function SidePanel(): JSX.Element {
  return (
    <aside className="side-panel" aria-label="Analysis">
      <CriticalPanel />
      <TopUtilizedPanel />
      <ImpactPanel />
    </aside>
  );
}
