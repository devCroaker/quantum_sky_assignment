import { feature } from 'topojson-client';
import type { Topology } from 'topojson-specification';
import type { FeatureCollection } from 'geojson';

// world-atlas is the public-domain Natural Earth dataset (D3's own choice of basemap
// source). The 110m resolution is the coarsest it ships, which is the point: D3 asks for
// a faint outline for orientation, not decoration, and the topology drawn on top is the
// subject. A finer resolution would also draw coastline detail at a scale where the
// network map never zooms in far enough to need it.
import landTopology from 'world-atlas/land-110m.json';

// The generated wire types are hand-cast like this too (src/api/guards.ts): a JSON import
// has no declared TopoJSON shape, and `Topology` is a type-only contract from the
// `topojson-specification` package, not something a library validates at runtime.
const topology = landTopology as unknown as Topology;
const landObject = topology.objects['land'];
if (landObject === undefined || landObject.type !== 'GeometryCollection') {
  throw new Error('world-atlas/land-110m.json: expected a "land" GeometryCollection');
}

/**
 * The world's land mass as one GeoJSON feature collection, converted once at module load
 * rather than per render, since the topology never changes.
 */
export const landFeatures: FeatureCollection = feature(topology, landObject);
