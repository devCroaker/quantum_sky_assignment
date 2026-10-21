import type { JSX, ReactNode } from 'react';
import { useMemo, useState } from 'react';

import type { ElementRef } from './selectionContext';
import { SelectionContext, sameElement } from './selectionContext';

/**
 * One piece of shared state for "what is highlighted", read and written by the map and by
 * every panel row.
 *
 * R10 requires the map and the panels to agree on highlighting a row or a marker, in either
 * direction, and R11 (P18) needs the same mechanism to mark the element about to be failed.
 * Keeping it to a single `ElementRef | null` behind a context, rather than one state slot
 * per component, is what lets both land without the map and a panel disagreeing about which
 * element is current, and lets P18 reuse this hook rather than inventing its own.
 */
export function SelectionProvider({ children }: { children: ReactNode }): JSX.Element {
  const [highlighted, setHighlighted] = useState<ElementRef | null>(null);
  const value = useMemo(
    () => ({
      highlighted,
      setHighlighted,
      isHighlighted: (ref: ElementRef) => sameElement(highlighted, ref),
    }),
    [highlighted],
  );
  return <SelectionContext.Provider value={value}>{children}</SelectionContext.Provider>;
}
