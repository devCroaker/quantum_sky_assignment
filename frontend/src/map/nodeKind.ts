import type { NodeKind } from '../api/types';

/**
 * D21 applies to the whole map, not only to P17's overlays: every node kind must be
 * distinguishable by shape, not only by colour. This map is the single place that
 * decision lives, read by the glyph that draws the shape and by anything else (tests,
 * the popover) that needs to name it in words.
 */
const SHAPE_BY_KIND: Record<NodeKind, string> = {
  'backbone-city': 'circle',
  'data-center': 'square',
  'operations-site': 'triangle',
  'aggregation-hub': 'diamond',
};

const KIND_LABEL: Record<NodeKind, string> = {
  'backbone-city': 'backbone city',
  'data-center': 'data center',
  'operations-site': 'operations site',
  'aggregation-hub': 'aggregation hub',
};

export function glyphShapeFor(kind: NodeKind): string {
  return SHAPE_BY_KIND[kind];
}

export function kindLabelFor(kind: NodeKind): string {
  return KIND_LABEL[kind];
}
