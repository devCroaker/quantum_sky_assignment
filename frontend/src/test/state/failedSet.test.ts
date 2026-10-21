import { describe, expect, it } from 'vitest';

import {
  matchesReport,
  NOTHING_FAILED,
  toScenarioRequest,
  withRestored,
  withToggled,
} from '../../state/failedSet';

const berlin = { kind: 'node', id: 'Berlin' } as const;
const warsaw = { kind: 'node', id: 'Warsaw' } as const;
const link = { kind: 'link', id: 'L4' } as const;

describe('the failed set', () => {
  it('toggling an element adds it, and toggling it again removes it', () => {
    const failed = withToggled(NOTHING_FAILED, berlin);
    expect(failed.failedNodes).toEqual(['Berlin']);
    expect(withToggled(failed, berlin)).toEqual(NOTHING_FAILED);
  });

  it('keeps nodes and links apart, so a node and a link can share an id without clashing', () => {
    const failed = withToggled(NOTHING_FAILED, link);
    expect(failed.failedLinks).toEqual(['L4']);
    expect(failed.failedNodes).toEqual([]);
  });

  it('keeps each list sorted, so the same set always makes the same request', () => {
    const one = withToggled(withToggled(NOTHING_FAILED, warsaw), berlin);
    const two = withToggled(withToggled(NOTHING_FAILED, berlin), warsaw);
    expect(one.failedNodes).toEqual(['Berlin', 'Warsaw']);
    expect(toScenarioRequest(one)).toEqual(toScenarioRequest(two));
  });

  it('restores one element and leaves the rest failed', () => {
    const failed = withToggled(withToggled(NOTHING_FAILED, berlin), warsaw);
    expect(withRestored(failed, berlin).failedNodes).toEqual(['Warsaw']);
  });

  it('serialises to the two arrays the contract names, empty when nothing has failed', () => {
    expect(toScenarioRequest(NOTHING_FAILED)).toEqual({
      failed_nodes: [],
      failed_links: [],
    });
    expect(toScenarioRequest(withToggled(NOTHING_FAILED, berlin))).toEqual({
      failed_nodes: ['Berlin'],
      failed_links: [],
    });
  });

  it('matches a report to the set it was computed for, ignoring order and absent keys', () => {
    const failed = withToggled(withToggled(NOTHING_FAILED, warsaw), berlin);
    expect(matchesReport(failed, { nodes: ['Warsaw', 'Berlin'] })).toBe(true);
    expect(matchesReport(failed, { nodes: ['Berlin'] })).toBe(false);
    expect(matchesReport(NOTHING_FAILED, {})).toBe(true);
  });
});
