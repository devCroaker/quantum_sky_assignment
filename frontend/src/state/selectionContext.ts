import { createContext, useContext } from 'react';

import type { ElementKind } from '../api/types';

/** Identifies one node or one link, the unit the map and the panels both select. */
export interface ElementRef {
  readonly kind: ElementKind;
  readonly id: string;
}

export function sameElement(a: ElementRef | null, b: ElementRef): boolean {
  return a !== null && a.kind === b.kind && a.id === b.id;
}

export interface SelectionContextValue {
  /** The element currently highlighted, from either the map or a panel row. */
  readonly highlighted: ElementRef | null;
  readonly setHighlighted: (ref: ElementRef | null) => void;
  readonly isHighlighted: (ref: ElementRef) => boolean;
}

export const SelectionContext = createContext<SelectionContextValue | null>(null);

export function useSelection(): SelectionContextValue {
  const context = useContext(SelectionContext);
  if (context === null) {
    throw new Error('useSelection must be used within a SelectionProvider');
  }
  return context;
}

/**
 * Hover and focus events set the highlight; they also clear it again on leaving, but only
 * if nothing else (a click, or another element's hover) has since taken over. Returning this
 * bundle from one place is what keeps a node glyph, a link line and a panel row wiring the
 * same five handlers the same way, rather than each re-deriving the "don't clear someone
 * else's highlight" guard.
 */
export function useHighlightHandlers(ref: ElementRef): {
  readonly highlighted: boolean;
  readonly onPointerEnter: () => void;
  readonly onPointerLeave: () => void;
  readonly onFocus: () => void;
  readonly onBlur: () => void;
  readonly onSelect: () => void;
} {
  const { isHighlighted, setHighlighted } = useSelection();
  const highlighted = isHighlighted(ref);
  return {
    highlighted,
    onPointerEnter: () => {
      setHighlighted(ref);
    },
    onPointerLeave: () => {
      if (isHighlighted(ref)) setHighlighted(null);
    },
    onFocus: () => {
      setHighlighted(ref);
    },
    onBlur: () => {
      if (isHighlighted(ref)) setHighlighted(null);
    },
    onSelect: () => {
      setHighlighted(ref);
    },
  };
}
