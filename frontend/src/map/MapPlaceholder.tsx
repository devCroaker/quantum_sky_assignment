import type { JSX } from 'react';

import type { NetworkResponse } from '../api/types';

/**
 * Placeholder for the map, which lands in P16 and answers R9.
 *
 * P16 replaces the body of this component with a d3-geo projection of the node positions,
 * a faint Natural Earth outline, the links, and a node glyph that varies by kind. The
 * component keeps this signature: it receives the network and renders it, and computes no
 * placement of its own, because geometry belongs to the back end.
 *
 * It lists the nodes for now so that there is something real on screen and so the layout
 * is exercised at the size the full network will need, 37 nodes and 55 links.
 */
export function MapPlaceholder({ network }: { network: NetworkResponse }): JSX.Element {
  return (
    <section className="map" aria-labelledby="map-heading">
      <h2 id="map-heading">Map</h2>
      <p className="placeholder-note">
        The map renders here in P16: coordinates projected with d3-geo, a node glyph per
        kind, pan and zoom.
      </p>
      <ul className="node-list">
        {network.nodes.map((node) => (
          <li key={node.id}>
            {/*
              A real button rather than a clickable div, and deliberately not disabled.
              P18 makes selecting a node fail it, and every element that becomes clickable
              then has to be reachable by keyboard, so the placeholder is already
              focusable and already announces what it is.
            */}
            <button type="button" className="node-chip">
              <span className="node-chip-id">{node.id}</span>
              <span className="node-chip-kind">{node.kind}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
