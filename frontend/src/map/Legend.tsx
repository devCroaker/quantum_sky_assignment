import type { JSX } from 'react';

/**
 * Names every non-colour encoding D21 puts on the map, so a reader never has to infer what
 * a dashed line or a numbered badge means from the map alone.
 *
 * Each row pairs a small drawing of the real marks (not a colour swatch) with the words for
 * it, because the whole point of D21 is that the shape and the stroke carry the meaning.
 */
export function Legend(): JSX.Element {
  return (
    <div className="map-legend" role="note" aria-label="Map legend">
      <div className="map-legend-item">
        <svg className="map-legend-glyph" viewBox="-14 -14 28 28" aria-hidden="true">
          <circle className="critical-ring" r={13} />
          <circle r={7} className="map-legend-node" />
          <g className="critical-marker" transform="translate(11,-11)">
            <polygon className="critical-marker-triangle" points="0,-5 4.3,3 -4.3,3" />
            <text className="critical-marker-bang" y={2.4}>
              !
            </text>
          </g>
        </svg>
        <span>Critical node: dashed ring plus a warning marker</span>
      </div>
      <div className="map-legend-item">
        {/*
          Not `.link` here: this swatch demonstrates the dash pattern without being a real
          link, and MapView.test.tsx counts `.link` elements to prove it draws one per
          fixture link, a count this decorative line would otherwise throw off.
        */}
        <svg className="map-legend-glyph" viewBox="0 0 28 28" aria-hidden="true">
          <line
            className="map-legend-link link-critical"
            x1={2}
            y1={14}
            x2={26}
            y2={14}
          />
        </svg>
        <span>Critical link: dashed stroke</span>
      </div>
      <div className="map-legend-item">
        <svg className="map-legend-glyph" viewBox="0 0 28 28" aria-hidden="true">
          <line
            className="map-legend-link link-top-utilized"
            x1={2}
            y1={14}
            x2={26}
            y2={14}
          />
          <g className="rank-badge" transform="translate(14,14)">
            <circle r={7} />
            <text y={3}>1</text>
          </g>
        </svg>
        <span>
          Among the five most utilized links: numbered badge (1 to 5) and a heavier stroke
        </span>
      </div>
    </div>
  );
}
