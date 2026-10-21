import type { Assessment, CriticalityReason } from '../api/types';

export const REASONS: readonly CriticalityReason[] = [
  'partitions-network',
  'demands-undeliverable',
  'links-overloaded',
];

export const REASON_LABEL: Record<CriticalityReason, string> = {
  'partitions-network': 'Partitions the network',
  'demands-undeliverable': 'Leaves a demand undeliverable',
  'links-overloaded': 'Overloads a surviving link',
};

/**
 * Every reason is shown by default, because every reason now describes harm to
 * somebody else: the element partitions the network, strands a demand between
 * two surviving nodes, or drives a surviving link over capacity.
 *
 * This used to be a filter that hid noise. A fourth reason, `endpoint-demands-lost`,
 * made an element critical merely for originating traffic, which marked 37 of the
 * real network's 37 nodes critical and left the panel's default view as the only
 * way to see the few that mattered. The panel reverted that reading, so the noise
 * is gone and these checkboxes narrow rather than rescue: a reader who wants only
 * the elements that partition the network can ask for those alone.
 */
export const DEFAULT_REASONS: ReadonlySet<CriticalityReason> = new Set([
  'partitions-network',
  'demands-undeliverable',
  'links-overloaded',
]);

export function countsByReason(
  assessments: readonly Assessment[],
): Record<CriticalityReason, number> {
  const counts: Record<CriticalityReason, number> = {
    'partitions-network': 0,
    'demands-undeliverable': 0,
    'links-overloaded': 0,
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
