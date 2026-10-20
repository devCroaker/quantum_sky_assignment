import type { KeyboardEvent, RefObject } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { select } from 'd3-selection';
import { zoom as d3zoom, zoomIdentity } from 'd3-zoom';
import type { D3ZoomEvent, ZoomBehavior, ZoomTransform } from 'd3-zoom';

const MIN_SCALE = 1;
const MAX_SCALE = 16;

/** How far one keypress pans, in the same SVG user units the projection draws in. */
const KEYBOARD_PAN_PX = 60;
const KEYBOARD_ZOOM_FACTOR = 1.4;

/**
 * Pan and zoom for the map, resolving the one real hazard of using `d3-zoom` inside React:
 * the two libraries must not both own the transform.
 *
 * `d3-zoom` is used here purely as gesture recognition. It owns the DOM's native wheel,
 * drag and touch listeners (attached once, imperatively, to the SVG element) and it owns
 * the arithmetic of turning a gesture into a transform, including its own internal
 * bookkeeping of "the current transform" that it keeps on the DOM node. It never writes
 * anything to the page itself. React owns every pixel that reaches the screen: the `zoom`
 * event is the only channel from d3 to React, each event's `transform` is copied into
 * React state, and the component tree renders that state on the next pass, the same as any
 * other prop. There is exactly one writer of the `<g transform>` attribute, which is React,
 * and exactly one source of gesture math, which is d3. Keyboard panning and zooming reuse
 * the same channel: a keydown handler calls the behavior's own `translateBy` / `scaleBy`
 * against the bound selection, which raises the same `zoom` event the mouse would have, so
 * there is still only one path from "something happened" to "the view changed".
 */
export function useZoomPan(svgRef: RefObject<SVGSVGElement | null>): {
  transform: ZoomTransform;
  onKeyDown: (event: KeyboardEvent<SVGSVGElement>) => void;
} {
  const [transform, setTransform] = useState<ZoomTransform>(zoomIdentity);

  const behavior = useMemo<ZoomBehavior<SVGSVGElement, unknown>>(
    () => d3zoom<SVGSVGElement, unknown>().scaleExtent([MIN_SCALE, MAX_SCALE]),
    [],
  );

  useEffect(() => {
    const svg = svgRef.current;
    if (svg === null) return;
    const selection = select(svg);
    behavior.on('zoom', (event: D3ZoomEvent<SVGSVGElement, unknown>) => {
      setTransform(event.transform);
    });
    selection.call(behavior);
    return () => {
      selection.on('.zoom', null);
    };
  }, [svgRef, behavior]);

  function onKeyDown(event: KeyboardEvent<SVGSVGElement>): void {
    const svg = svgRef.current;
    if (svg === null) return;
    const selection = select(svg);
    switch (event.key) {
      case 'ArrowUp':
        behavior.translateBy(selection, 0, KEYBOARD_PAN_PX);
        break;
      case 'ArrowDown':
        behavior.translateBy(selection, 0, -KEYBOARD_PAN_PX);
        break;
      case 'ArrowLeft':
        behavior.translateBy(selection, KEYBOARD_PAN_PX, 0);
        break;
      case 'ArrowRight':
        behavior.translateBy(selection, -KEYBOARD_PAN_PX, 0);
        break;
      case '+':
      case '=':
        behavior.scaleBy(selection, KEYBOARD_ZOOM_FACTOR);
        break;
      case '-':
      case '_':
        behavior.scaleBy(selection, 1 / KEYBOARD_ZOOM_FACTOR);
        break;
      default:
        return;
    }
    event.preventDefault();
  }

  return { transform, onKeyDown };
}
