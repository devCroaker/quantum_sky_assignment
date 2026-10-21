import type { KeyboardEvent } from 'react';
import { createContext, useContext } from 'react';

import type { FailureSet } from './failedSet';
import { NOTHING_FAILED } from './failedSet';
import type { ElementRef } from './selectionContext';

/**
 * What the App shares with the map and the panels about failures. App owns the state and
 * the requests; this context only carries them down, so no view posts a scenario itself.
 */
export interface FailureContextValue {
  readonly failed: FailureSet;
  readonly isFailed: (ref: ElementRef) => boolean;
  readonly toggle: (ref: ElementRef) => void;
  readonly restore: (ref: ElementRef) => void;
  readonly restoreAll: () => void;
}

/**
 * The default is inert: nothing failed, and every action does nothing. It exists so a view
 * rendered on its own, in a test, still renders. The App always supplies the real value.
 */
const INERT: FailureContextValue = {
  failed: NOTHING_FAILED,
  isFailed: () => false,
  toggle: () => undefined,
  restore: () => undefined,
  restoreAll: () => undefined,
};

export const FailureContext = createContext<FailureContextValue>(INERT);

export function useFailures(): FailureContextValue {
  return useContext(FailureContext);
}

/**
 * Everything a focusable element needs to fail and restore itself: whether it is failed, a
 * click handler, and a key handler that treats Enter and Space as the same click, which is
 * the keyboard half of R11. A native `<button>` gets Enter and Space from the browser and
 * needs only `toggle` on its click, so it does not wire the key handler.
 */
export function useFailureToggle(ref: ElementRef): {
  readonly failed: boolean;
  readonly toggle: () => void;
  readonly onKeyDown: (event: KeyboardEvent) => void;
} {
  const { isFailed, toggle } = useFailures();
  return {
    failed: isFailed(ref),
    toggle: () => {
      toggle(ref);
    },
    onKeyDown: (event) => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      // Stops Space from scrolling the page while an SVG element has focus.
      event.preventDefault();
      toggle(ref);
    },
  };
}
