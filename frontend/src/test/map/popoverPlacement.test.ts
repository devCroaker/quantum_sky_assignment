/**
 * Regression tests for where the cluster popover goes.
 *
 * The case that matters is the bottom right corner. The original code flipped
 * to `bottom: 100%` there, which is relative to the map container rather than
 * to the marker, so the popover landed at the top of the map about 600 pixels
 * from the node it described. Every test still passed, because nothing measured
 * the result. These numbers come from the real rendered sizes observed in the
 * browser when that bug was found.
 */
import { describe, expect, it } from 'vitest';

import { ANCHOR_GAP_PX, EDGE_MARGIN_PX, placePopover } from '../../map/popoverPlacement';

// Observed in the browser: the popover renders about this size for two entries,
// inside a map canvas of roughly this size.
const SIZE = { width: 176, height: 157 };
const CANVAS = { containerWidth: 633, containerHeight: 580 };

describe('placePopover', () => {
  it('sits below and to the right of a marker with room around it', () => {
    const placement = placePopover({
      anchorLeftPx: 100,
      anchorTopPx: 100,
      ...SIZE,
      ...CANVAS,
    });
    expect(placement).toEqual({
      left: 100 + ANCHOR_GAP_PX,
      top: 100 + ANCHOR_GAP_PX,
    });
  });

  it('stays beside a marker in the bottom right corner, not at the container edge', () => {
    // The exact case that was broken. The marker sat near (629, 575) inside the
    // canvas and the popover was placed at the top of the map.
    const anchorLeftPx = 629;
    const anchorTopPx = 575;
    const placement = placePopover({ anchorLeftPx, anchorTopPx, ...SIZE, ...CANVAS });

    // Mirrored to the other side of the marker rather than pinned to an edge.
    expect(placement.left).toBeLessThan(anchorLeftPx);
    expect(placement.top).toBeLessThan(anchorTopPx);

    // And still touching it: every corner within a short distance of the anchor.
    const dx = Math.min(
      Math.abs(placement.left - anchorLeftPx),
      Math.abs(placement.left + SIZE.width - anchorLeftPx),
    );
    const dy = Math.min(
      Math.abs(placement.top - anchorTopPx),
      Math.abs(placement.top + SIZE.height - anchorTopPx),
    );
    expect(Math.hypot(dx, dy)).toBeLessThan(40);
  });

  it('never leaves the container on any side', () => {
    const corners = [
      [0, 0],
      [633, 0],
      [0, 580],
      [633, 580],
      [316, 290],
    ] as const;
    for (const [anchorLeftPx, anchorTopPx] of corners) {
      const placement = placePopover({ anchorLeftPx, anchorTopPx, ...SIZE, ...CANVAS });
      expect(placement.left).toBeGreaterThanOrEqual(EDGE_MARGIN_PX);
      expect(placement.top).toBeGreaterThanOrEqual(EDGE_MARGIN_PX);
      expect(placement.left + SIZE.width).toBeLessThanOrEqual(CANVAS.containerWidth);
      expect(placement.top + SIZE.height).toBeLessThanOrEqual(CANVAS.containerHeight);
    }
  });

  it('clamps rather than going negative when the popover is larger than the container', () => {
    const placement = placePopover({
      anchorLeftPx: 10,
      anchorTopPx: 10,
      width: 900,
      height: 900,
      ...CANVAS,
    });
    expect(placement).toEqual({ left: EDGE_MARGIN_PX, top: EDGE_MARGIN_PX });
  });
});
