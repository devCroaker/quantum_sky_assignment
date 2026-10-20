import type { JSX, KeyboardEvent } from 'react';
import { useEffect, useRef } from 'react';

import type { NodeWire } from '../api/types';
import { kindLabelFor } from './nodeKind';
import { placePopover } from './popoverPlacement';

/**
 * The reviewer's cluster popover (not a plan requirement; recorded in the task brief
 * rather than in docs/DECISIONS.md, since that document is reserved for decisions the
 * panel or the tool made about the plan itself).
 *
 * Positioned from the marker's measured offset within the map canvas, in pixels,
 * which is why it works at any rendered size without a ResizeObserver: the percentage is
 * computed from the same `viewBox` coordinates the SVG draws in.
 */
export function ClusterPopover({
  nodes,
  anchorLeftPx,
  anchorTopPx,
  onClose,
  onSelectNode,
  onRequestReturnFocus,
  onMouseEnter,
  onMouseLeave,
}: {
  nodes: readonly NodeWire[];
  anchorLeftPx: number;
  anchorTopPx: number;
  onClose: () => void;
  onSelectNode: (id: string) => void;
  /**
   * Called on Escape so the marker that opened this popover can take focus back. A
   * callback rather than a ref to the marker: reading a ref's `.current` during render
   * is unsound (it can be stale or null depending on commit order), and this is only ever
   * needed from the Escape key handler, never during render.
   */
  onRequestReturnFocus: () => void;
  /**
   * The popover and its marker share one "is the pointer over either of us" timer, owned
   * by the caller, so crossing the gap between them does not close and reopen the
   * popover: see MapView's `scheduleClose`/`cancelClose` for why a plain `onMouseLeave`
   * on either element alone would flicker.
   */
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}): JSX.Element {
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Opening by focus or by hover both land here; either way the first entry takes focus,
  // so arrow keys have somewhere to start from without a pointer ever being involved.
  useEffect(() => {
    itemRefs.current[0]?.focus();
  }, []);

  // Keep the popover beside its anchor and inside the map.
  //
  // The obvious way to handle an overflow is to flip to `right: 0` or
  // `bottom: 100%`, but those are relative to the positioned ancestor, not to
  // the anchor, so they throw the anchor away: a marker in the bottom right
  // corner ended up with its popover pinned to the top of the map, hundreds of
  // pixels from the node it describes. So this places the popover on the other
  // side of the anchor instead, and only then clamps it into the container.
  //
  // Styles are written to the DOM rather than held in state because the
  // measurement depends on the rendered size of this element, which is not
  // known until after it has been laid out.
  useEffect(() => {
    const el = containerRef.current;
    if (el === null) return;
    const parent = el.offsetParent;
    if (!(parent instanceof HTMLElement)) return;
    const { left, top } = placePopover({
      anchorLeftPx,
      anchorTopPx,
      width: el.offsetWidth,
      height: el.offsetHeight,
      containerWidth: parent.clientWidth,
      containerHeight: parent.clientHeight,
    });
    el.style.left = `${String(left)}px`;
    el.style.top = `${String(top)}px`;
  }, [anchorLeftPx, anchorTopPx]);

  function focusIndex(index: number): void {
    const bounded = (index + nodes.length) % nodes.length;
    itemRefs.current[bounded]?.focus();
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const currentIndex = itemRefs.current.findIndex(
      (el) => el === document.activeElement,
    );
    switch (event.key) {
      case 'Escape':
        event.stopPropagation();
        onClose();
        onRequestReturnFocus();
        break;
      case 'ArrowDown':
      case 'ArrowRight':
        event.preventDefault();
        focusIndex(currentIndex === -1 ? 0 : currentIndex + 1);
        break;
      case 'ArrowUp':
      case 'ArrowLeft':
        event.preventDefault();
        focusIndex(currentIndex === -1 ? 0 : currentIndex - 1);
        break;
      default:
        break;
    }
  }

  return (
    <div
      ref={containerRef}
      className="cluster-popover"
      role="menu"
      aria-label={`${String(nodes.length)} nodes at this position`}
      style={{ left: `${String(anchorLeftPx)}px`, top: `${String(anchorTopPx)}px` }}
      onKeyDown={onKeyDown}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
    >
      <ul className="cluster-popover-list">
        {nodes.map((node, index) => (
          <li key={node.id}>
            <button
              type="button"
              role="menuitem"
              ref={(el) => {
                itemRefs.current[index] = el;
              }}
              className="cluster-popover-item"
              onClick={() => {
                onSelectNode(node.id);
              }}
            >
              <span className="cluster-popover-id">{node.id}</span>
              <span className="cluster-popover-kind">{kindLabelFor(node.kind)}</span>
              {node.attaches_to !== undefined && node.attaches_to.length > 0 ? (
                <span className="cluster-popover-attaches">
                  attaches to {node.attaches_to.join(', ')}
                </span>
              ) : null}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
