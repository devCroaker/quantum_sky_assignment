import type { ScenarioRequest } from '../api/types';
import type { ElementRef } from './selectionContext';

/**
 * The set of elements the user has failed, owned by the front end (docs/api-contract.md,
 * decision 2). The API keeps no session, so this is the only copy: it is sent whole with
 * every scenario request, and restoring everything is simply sending two empty lists.
 *
 * Kept as plain functions over an immutable value so the rule for toggling and restoring
 * is one tested place rather than something each map glyph and panel row re-derives.
 */
export interface FailureSet {
  readonly failedNodes: readonly string[];
  readonly failedLinks: readonly string[];
}

export const NOTHING_FAILED: FailureSet = { failedNodes: [], failedLinks: [] };

export function isFailedIn(set: FailureSet, ref: ElementRef): boolean {
  const list = ref.kind === 'node' ? set.failedNodes : set.failedLinks;
  return list.includes(ref.id);
}

export function isNothingFailed(set: FailureSet): boolean {
  return set.failedNodes.length === 0 && set.failedLinks.length === 0;
}

export function withToggled(set: FailureSet, ref: ElementRef): FailureSet {
  return isFailedIn(set, ref) ? withRestored(set, ref) : withFailed(set, ref);
}

/**
 * Kept sorted so the request body for a given set is the same however the set was reached,
 * which makes a scenario reproducible from its request alone, as the contract intends.
 */
function withFailed(set: FailureSet, ref: ElementRef): FailureSet {
  if (ref.kind === 'node') {
    return { ...set, failedNodes: [...set.failedNodes, ref.id].sort() };
  }
  return { ...set, failedLinks: [...set.failedLinks, ref.id].sort() };
}

export function withRestored(set: FailureSet, ref: ElementRef): FailureSet {
  if (ref.kind === 'node') {
    return { ...set, failedNodes: set.failedNodes.filter((id) => id !== ref.id) };
  }
  return { ...set, failedLinks: set.failedLinks.filter((id) => id !== ref.id) };
}

export function toScenarioRequest(set: FailureSet): ScenarioRequest {
  return { failed_nodes: [...set.failedNodes], failed_links: [...set.failedLinks] };
}

/** Whether a report's own record of the set it answers names the same elements as `set`. */
export function matchesReport(
  set: FailureSet,
  reported: { nodes?: string[]; links?: string[] },
): boolean {
  return (
    sameIds(set.failedNodes, reported.nodes ?? []) &&
    sameIds(set.failedLinks, reported.links ?? [])
  );
}

function sameIds(a: readonly string[], b: readonly string[]): boolean {
  if (a.length !== b.length) return false;
  const left = [...a].sort();
  const right = [...b].sort();
  return left.every((id, index) => id === right[index]);
}
