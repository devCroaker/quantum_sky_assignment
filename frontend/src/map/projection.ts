import { geoAzimuthalEqualArea } from 'd3-geo';
import type { GeoProjection } from 'd3-geo';
import type { FeatureCollection, Point } from 'geojson';

import type { NodeWire } from '../api/types';

/**
 * The logical drawing surface. The SVG uses this as its `viewBox`, scaled to the
 * container by CSS, so every computed coordinate in this module is independent of the
 * element's actual rendered size.
 */
export const MAP_WIDTH = 960;
export const MAP_HEIGHT = 640;

/** Breathing room so a node at the edge of the data is not drawn on the viewBox border. */
const FIT_PADDING = 24;

/**
 * Centre of the azimuthal projection, roughly the middle of the merged network's
 * footprint (Dublin to Athens, Madrid to Warsaw). Chosen by eye against the real
 * `nobel-eu` coordinates, not computed, since the center of an azimuthal projection is a
 * drawing choice rather than a derived fact.
 */
const EUROPE_CENTER: readonly [number, number] = [10, 50];

/**
 * D3. Map rendering picked inline SVG with `d3-geo` over a basemap. This module picks
 * which projection within that family.
 *
 * Chosen: `geoAzimuthalEqualArea`, rotated so its tangent point sits over central Europe.
 * This mirrors the real cartographic standard for the continent: ETRS89-LAEA (EPSG:3035),
 * the projection Eurostat uses for every official European map, is an oblique azimuthal
 * equal-area projection centred near 52N, 10E. A conic projection (the other common
 * choice for a mid-latitude region) is tuned for an east-west band and would waste
 * accuracy on the network's Dublin-to-Athens, Madrid-to-Warsaw spread, which runs on both
 * axes at once. Equal-area also means the land outline keeps its proportions, which
 * matters more here than preserving angles, since nothing on this map is navigated by
 * compass bearing.
 *
 * The projection is fit to the actual node set with `fitExtent` rather than given a fixed
 * scale and translate, so it works unchanged for the seven-node fixture and the full
 * 37-node network alike: both are European networks, just different crops of the same
 * continent.
 */
export function createProjection(
  nodes: readonly Pick<NodeWire, 'position'>[],
  width: number = MAP_WIDTH,
  height: number = MAP_HEIGHT,
): GeoProjection {
  const points: FeatureCollection<Point> = {
    type: 'FeatureCollection',
    features: nodes.map((node) => ({
      type: 'Feature',
      properties: null,
      geometry: { type: 'Point', coordinates: [node.position.x, node.position.y] },
    })),
  };

  return geoAzimuthalEqualArea()
    .rotate([-EUROPE_CENTER[0], -EUROPE_CENTER[1]])
    .fitExtent(
      [
        [FIT_PADDING, FIT_PADDING],
        [width - FIT_PADDING, height - FIT_PADDING],
      ],
      points,
    );
}
