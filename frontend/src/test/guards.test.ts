import { describe, expect, it } from 'vitest';

import networkFixture from '@contracts/fixtures/network.json';

import {
  WireFormatError,
  parseNetworkResponse,
  parseScenarioReport,
} from '../api/guards';

/** A deep copy, so one case cannot damage the fixture for the next. */
function copyNetwork(): Record<string, unknown> {
  return JSON.parse(JSON.stringify(networkFixture)) as Record<string, unknown>;
}

describe('the wire guards', () => {
  it('accept the committed fixture unchanged', () => {
    expect(() => parseNetworkResponse(networkFixture)).not.toThrow();
  });

  it('reject a node missing a required field, naming the path', () => {
    const payload = copyNetwork();
    const nodes = payload['nodes'] as Record<string, unknown>[];
    delete nodes[0]?.['can_transit'];

    expect(() => parseNetworkResponse(payload)).toThrow(WireFormatError);
    // The point of the guards is that the failure names the offending field rather than
    // surfacing later as an undefined inside a component.
    expect(() => parseNetworkResponse(payload)).toThrow(
      /NetworkResponse\.nodes\[0\]\.can_transit: expected a boolean, got undefined/,
    );
  });

  it('reject an unknown enum value', () => {
    const payload = copyNetwork();
    const nodes = payload['nodes'] as Record<string, unknown>[];
    const first = nodes[0];
    if (first === undefined) throw new Error('the fixture has no nodes');
    first['kind'] = 'teapot';

    expect(() => parseNetworkResponse(payload)).toThrow(/\.kind: expected one of/);
  });

  it('reject an endpoint pair that is not a pair', () => {
    const payload = copyNetwork();
    const links = payload['links'] as Record<string, unknown>[];
    const first = links[0];
    if (first === undefined) throw new Error('the fixture has no links');
    first['endpoints'] = ['Berlin'];

    expect(() => parseNetworkResponse(payload)).toThrow(/expected exactly two node ids/);
  });

  it('reject a payload of the wrong shape entirely', () => {
    expect(() => parseScenarioReport(null)).toThrow(/expected an object, got null/);
    expect(() => parseScenarioReport([])).toThrow(/expected an object, got an array/);
  });
});
