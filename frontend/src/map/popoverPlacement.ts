/**
 * Where to put the cluster popover, as pure arithmetic.
 *
 * This lives apart from the component so it can be tested with real numbers.
 * The bug it exists to prevent was found by eye and not by a test: the original
 * placement handled an overflow by flipping to `right: 0` or `bottom: 100%`,
 * which are relative to the positioned ancestor rather than to the anchor. A
 * marker in the bottom right corner of the map therefore had its popover pinned
 * to the top of the map, roughly 600 pixels from the node it was describing,
 * while every unit test still passed.
 *
 * The rule here is: prefer below and to the right of the marker, mirror to the
 * other side of the marker when that does not fit, and only then clamp into the
 * container. Mirroring keeps the popover touching the thing it describes, which
 * flipping to a container edge does not.
 */

/** Breathing room so the popover never touches the edge of the map. */
export const EDGE_MARGIN_PX = 8;

/** Offset from the marker, small enough that the two read as one object. */
export const ANCHOR_GAP_PX = 12;

export interface PlacementInput {
  anchorLeftPx: number;
  anchorTopPx: number;
  width: number;
  height: number;
  containerWidth: number;
  containerHeight: number;
}

export interface Placement {
  left: number;
  top: number;
}

function place(anchor: number, size: number, container: number): number {
  const max = container - size - EDGE_MARGIN_PX;
  let value = anchor + ANCHOR_GAP_PX;
  if (value > max) {
    // Mirror to the other side of the anchor rather than to the container edge.
    value = anchor - size - ANCHOR_GAP_PX;
  }
  if (value > max) value = max;
  return Math.max(EDGE_MARGIN_PX, value);
}

export function placePopover(input: PlacementInput): Placement {
  return {
    left: place(input.anchorLeftPx, input.width, input.containerWidth),
    top: place(input.anchorTopPx, input.height, input.containerHeight),
  };
}
