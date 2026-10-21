import { fireEvent, render } from '@testing-library/react';
import type { JSX } from 'react';
import { describe, expect, it } from 'vitest';

import { useHighlightHandlers } from '../../state/selectionContext';
import { SelectionProvider } from '../../state/selection';

/**
 * A minimal stand-in for "a node glyph" or "a panel row": anything that calls
 * `useHighlightHandlers` for the same `ElementRef` is wired into the same shared state.
 * This is the mechanism MapView's glyphs and link lines, and CriticalPanel's and
 * TopUtilizedPanel's rows, all actually use; proving it here, independent of either one's
 * markup, is what shows the map and the panels cannot disagree about what is highlighted,
 * and is the hook P18 reuses for "select an element to fail it".
 */
function Marker({ id, label }: { id: string; label: string }): JSX.Element {
  const { highlighted, onPointerEnter, onPointerLeave, onSelect } = useHighlightHandlers({
    kind: 'node',
    id,
  });
  return (
    <button
      type="button"
      data-testid={label}
      aria-pressed={highlighted}
      onMouseEnter={onPointerEnter}
      onMouseLeave={onPointerLeave}
      onClick={onSelect}
    >
      {label}
    </button>
  );
}

describe('shared selection (the mechanism behind R10 and, later, R11)', () => {
  it('highlights every consumer of the same element ref together, map or panel', () => {
    const { getByTestId } = render(
      <SelectionProvider>
        <Marker id="Berlin" label="map-glyph" />
        <Marker id="Berlin" label="panel-row" />
        <Marker id="Hamburg" label="unrelated" />
      </SelectionProvider>,
    );
    const mapGlyph = getByTestId('map-glyph');
    const panelRow = getByTestId('panel-row');
    const unrelated = getByTestId('unrelated');

    expect(mapGlyph.getAttribute('aria-pressed')).toBe('false');
    expect(panelRow.getAttribute('aria-pressed')).toBe('false');

    // Hovering the "map" marker highlights the "panel" marker for the same element too.
    fireEvent.mouseEnter(mapGlyph);
    expect(mapGlyph.getAttribute('aria-pressed')).toBe('true');
    expect(panelRow.getAttribute('aria-pressed')).toBe('true');
    expect(unrelated.getAttribute('aria-pressed')).toBe('false');

    // And leaving it clears both again.
    fireEvent.mouseLeave(mapGlyph);
    expect(mapGlyph.getAttribute('aria-pressed')).toBe('false');
    expect(panelRow.getAttribute('aria-pressed')).toBe('false');

    // The reverse direction: selecting from the "panel" side highlights the "map" side.
    fireEvent.click(panelRow);
    expect(mapGlyph.getAttribute('aria-pressed')).toBe('true');
    expect(panelRow.getAttribute('aria-pressed')).toBe('true');
  });

  it('throws if used outside a SelectionProvider, rather than silently doing nothing', () => {
    function Unwrapped(): JSX.Element {
      return <Marker id="x" label="x" />;
    }
    // React logs this error to the console as part of throwing it; expected, not a leak.
    expect(() => render(<Unwrapped />)).toThrow(
      'useSelection must be used within a SelectionProvider',
    );
  });
});
