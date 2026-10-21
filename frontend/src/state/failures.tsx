import type { JSX, ReactNode } from 'react';

import type { FailureContextValue } from './failureContext';
import { FailureContext } from './failureContext';

/** Supplies the App's failure state and actions to everything underneath it. */
export function FailureProvider({
  value,
  children,
}: {
  value: FailureContextValue;
  children: ReactNode;
}): JSX.Element {
  return <FailureContext.Provider value={value}>{children}</FailureContext.Provider>;
}
