import type { Assessment, CriticalityReason } from '../api/types';

export const REASONS: readonly CriticalityReason[] = [
  'partitions-network',
  'demands-undeliverable',
  'links-overloaded',
  'endpoint-demands-lost',
];

export const REASON_LABEL: Record<CriticalityReason, string> = {
  'partitions-network': 'Partitions the network',
  'demands-undeliverable': 'Leaves a demand undeliverable',
  'links-overloaded': 'Overloads a surviving link',
  'endpoint-demands-lost': 'Only loses its own traffic',
};

/**
 * The structural reading of R7b, the default view: an element whose loss partitions the
 * network (`partitions-network`) or strands a demand somewhere else in it
 * (`demands-undeliverable`), as opposed to one that is critical only because it is the
 * endpoint of its own now-undeliverable demand (`endpoint-demands-lost`). This is docs/
 * api-contract.md decision 3b's own description of the genuine single points of failure.
 *
 * Built by OR-ing these two reasons in, never by subtracting `endpoint-demands-lost` out.
 * Subtracting it would also drop every node that carries it alongside a structural reason,
 * which on the real network is Athens, Dublin and Warsaw: the three nodes that both
 * partition the network AND originate their own traffic, and so exactly the nodes an
 * operations lead most needs to see. See CriticalPanel.test.tsx for the fabricated case
 * that tells the two readings apart; the committed 15-element fixture happens not to,
 * which is itself worth recording.
 *
 * `links-overloaded` (R7c) is a genuine failure mode too but is left off the default,
 * matching the two reasons named in decision 3b exactly; it is one checkbox away, with its
 * own count, for a reader who wants it.
 */
export const DEFAULT_REASONS: ReadonlySet<CriticalityReason> = new Set([
  'partitions-network',
  'demands-undeliverable',
]);

export function countsByReason(
  assessments: readonly Assessment[],
): Record<CriticalityReason, number> {
  const counts: Record<CriticalityReason, number> = {
    'partitions-network': 0,
    'demands-undeliverable': 0,
    'links-overloaded': 0,
    'endpoint-demands-lost': 0,
  };
  for (const assessment of assessments) {
    for (const reason of assessment.reasons ?? []) {
      counts[reason] += 1;
    }
  }
  return counts;
}

/**
 * Whether `assessment` should show under the given reason selection.
 *
 * Inclusive: shown when ANY of its reasons is selected. Never exclusive (shown unless a
 * deselected reason is present), because an element usually carries several reasons at
 * once, and an exclusive reading would drop it the moment it also happens to carry the
 * reason being hidden, rather than only when every one of its reasons is being hidden.
 */
export function matchesReasonFilter(
  assessment: Assessment,
  selected: ReadonlySet<CriticalityReason>,
): boolean {
  return (assessment.reasons ?? []).some((reason) => selected.has(reason));
}
