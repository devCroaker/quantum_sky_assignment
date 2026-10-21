/**
 * Hand-written guards for the generated wire types.
 *
 * Every payload crosses this module before any view sees it, whether it came from the
 * committed fixture or from the live API. The point is that a malformed payload fails
 * loudly, naming the field, at the one place that knows what the wire looks like, rather
 * than surfacing as an undefined deep inside a component during the demonstration.
 *
 * These are narrow on purpose. They check that the required fields of each wire model are
 * present and of the right primitive type, and that enum-valued fields hold one of the
 * documented values. They do not re-check the invariants the back end owns, such as
 * endpoints being sorted or utilization being load over capacity. No runtime validation
 * library is involved, which keeps the dependency list short enough to justify.
 */
import type {
  Assessment,
  CriticalityReason,
  CriticalityResponse,
  CriticalitySummary,
  ElementKind,
  FailedSet,
  FailureImpact,
  LinkKind,
  LinkLoad,
  LinkWire,
  NetworkResponse,
  NetworkTotals,
  NodeKind,
  NodeWire,
  Position,
  RankedLink,
  ScenarioReport,
  ScenarioTotals,
  StrandedDemand,
} from './types';

/** Thrown when a payload does not match the contract. `path` locates the offender. */
export class WireFormatError extends Error {
  readonly path: string;

  constructor(path: string, detail: string) {
    super(`${path}: ${detail}`);
    this.name = 'WireFormatError';
    this.path = path;
  }
}

type Json = Record<string, unknown>;

function fail(path: string, detail: string): never {
  throw new WireFormatError(path, detail);
}

function object(value: unknown, path: string): Json {
  if (typeof value !== 'object' || value === null || Array.isArray(value)) {
    fail(path, `expected an object, got ${describe(value)}`);
  }
  return value as Json;
}

function describe(value: unknown): string {
  if (value === null) return 'null';
  if (Array.isArray(value)) return 'an array';
  return typeof value;
}

function str(parent: Json, key: string, path: string): string {
  const value = parent[key];
  if (typeof value !== 'string') {
    fail(`${path}.${key}`, `expected a string, got ${describe(value)}`);
  }
  return value;
}

function num(parent: Json, key: string, path: string): number {
  const value = parent[key];
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    fail(`${path}.${key}`, `expected a finite number, got ${describe(value)}`);
  }
  return value;
}

function bool(parent: Json, key: string, path: string): boolean {
  const value = parent[key];
  if (typeof value !== 'boolean') {
    fail(`${path}.${key}`, `expected a boolean, got ${describe(value)}`);
  }
  return value;
}

function list(parent: Json, key: string, path: string): unknown[] {
  const value = parent[key];
  if (!Array.isArray(value)) {
    fail(`${path}.${key}`, `expected an array, got ${describe(value)}`);
  }
  return value;
}

/** An absent array field means the empty array, matching the schema defaults. */
function optionalStrings(parent: Json, key: string, path: string): string[] {
  const value = parent[key];
  if (value === undefined) return [];
  return strings({ [key]: value }, key, path);
}

function strings(parent: Json, key: string, path: string): string[] {
  return list(parent, key, path).map((item, index) => {
    if (typeof item !== 'string') {
      fail(
        `${path}.${key}[${String(index)}]`,
        `expected a string, got ${describe(item)}`,
      );
    }
    return item;
  });
}

function items<T>(
  parent: Json,
  key: string,
  path: string,
  parse: (value: unknown, path: string) => T,
): T[] {
  return list(parent, key, path).map((item, index) =>
    parse(item, `${path}.${key}[${String(index)}]`),
  );
}

function oneOf<T extends string>(value: string, allowed: readonly T[], path: string): T {
  const match = allowed.find((candidate) => candidate === value);
  if (match === undefined) {
    fail(path, `expected one of ${allowed.join(', ')}, got ${JSON.stringify(value)}`);
  }
  return match;
}

/** The two node ids of a link or demand. Order is the back end's business, per R3. */
function pair(parent: Json, key: string, path: string): [string, string] {
  const values = strings(parent, key, path);
  const [first, second] = values;
  if (values.length !== 2 || first === undefined || second === undefined) {
    fail(`${path}.${key}`, `expected exactly two node ids, got ${String(values.length)}`);
  }
  return [first, second];
}

const NODE_KINDS: readonly NodeKind[] = [
  'backbone-city',
  'data-center',
  'operations-site',
  'aggregation-hub',
];
const LINK_KINDS: readonly LinkKind[] = ['backbone', 'access'];
const ELEMENT_KINDS: readonly ElementKind[] = ['node', 'link'];
const CRITICALITY_REASONS: readonly CriticalityReason[] = [
  'partitions-network',
  'demands-undeliverable',
  'links-overloaded',
];

function parsePosition(value: unknown, path: string): Position {
  const raw = object(value, path);
  return { x: num(raw, 'x', path), y: num(raw, 'y', path) };
}

function parseNode(value: unknown, path: string): NodeWire {
  const raw = object(value, path);
  return {
    id: str(raw, 'id', path),
    kind: oneOf(str(raw, 'kind', path), NODE_KINDS, `${path}.kind`),
    position: parsePosition(raw['position'], `${path}.position`),
    can_transit: bool(raw, 'can_transit', path),
    attaches_to: optionalStrings(raw, 'attaches_to', path),
  };
}

function parseLink(value: unknown, path: string): LinkWire {
  const raw = object(value, path);
  return {
    id: str(raw, 'id', path),
    kind: oneOf(str(raw, 'kind', path), LINK_KINDS, `${path}.kind`),
    endpoints: pair(raw, 'endpoints', path),
    capacity: num(raw, 'capacity', path),
  };
}

function parseNetworkTotals(value: unknown, path: string): NetworkTotals {
  const raw = object(value, path);
  return {
    nodes: num(raw, 'nodes', path),
    links: num(raw, 'links', path),
    demands: num(raw, 'demands', path),
    demand_units: num(raw, 'demand_units', path),
  };
}

export function parseNetworkResponse(
  value: unknown,
  path = 'NetworkResponse',
): NetworkResponse {
  const raw = object(value, path);
  return {
    nodes: items(raw, 'nodes', path, parseNode),
    links: items(raw, 'links', path, parseLink),
    totals: parseNetworkTotals(raw['totals'], `${path}.totals`),
  };
}

function parseLinkLoad(value: unknown, path: string): LinkLoad {
  const raw = object(value, path);
  return {
    link_id: str(raw, 'link_id', path),
    load: num(raw, 'load', path),
    capacity: num(raw, 'capacity', path),
    utilization: num(raw, 'utilization', path),
  };
}

function parseRankedLink(value: unknown, path: string): RankedLink {
  return { ...parseLinkLoad(value, path), rank: num(object(value, path), 'rank', path) };
}

function parseStrandedDemand(value: unknown, path: string): StrandedDemand {
  const raw = object(value, path);
  return {
    id: str(raw, 'id', path),
    endpoints: pair(raw, 'endpoints', path),
    volume: num(raw, 'volume', path),
  };
}

function parseFailedSet(value: unknown, path: string): FailedSet {
  const raw = object(value, path);
  return {
    nodes: optionalStrings(raw, 'nodes', path),
    links: optionalStrings(raw, 'links', path),
  };
}

function parseScenarioTotals(value: unknown, path: string): ScenarioTotals {
  const raw = object(value, path);
  return {
    demands: num(raw, 'demands', path),
    units: num(raw, 'units', path),
    units_delivered: num(raw, 'units_delivered', path),
    units_undeliverable: num(raw, 'units_undeliverable', path),
    units_endpoint_affected: num(raw, 'units_endpoint_affected', path),
  };
}

export function parseScenarioReport(
  value: unknown,
  path = 'ScenarioReport',
): ScenarioReport {
  const raw = object(value, path);
  return {
    failed: parseFailedSet(raw['failed'], `${path}.failed`),
    partitioned: bool(raw, 'partitioned', path),
    components: num(raw, 'components', path),
    link_loads: items(raw, 'link_loads', path, parseLinkLoad),
    most_utilized: items(raw, 'most_utilized', path, parseRankedLink),
    overloaded_links: items(raw, 'overloaded_links', path, parseRankedLink),
    undeliverable_demands: items(raw, 'undeliverable_demands', path, parseStrandedDemand),
    endpoint_affected_demands: items(
      raw,
      'endpoint_affected_demands',
      path,
      parseStrandedDemand,
    ),
    totals: parseScenarioTotals(raw['totals'], `${path}.totals`),
  };
}

function parseFailureImpact(value: unknown, path: string): FailureImpact {
  const raw = object(value, path);
  return {
    components: num(raw, 'components', path),
    undeliverable_demands: num(raw, 'undeliverable_demands', path),
    undeliverable_units: num(raw, 'undeliverable_units', path),
    endpoint_affected_demands: num(raw, 'endpoint_affected_demands', path),
    endpoint_affected_units: num(raw, 'endpoint_affected_units', path),
    overloaded_links: num(raw, 'overloaded_links', path),
    max_utilization: num(raw, 'max_utilization', path),
  };
}

function parseAssessment(value: unknown, path: string): Assessment {
  const raw = object(value, path);
  const reasons = raw['reasons'];
  return {
    kind: oneOf(str(raw, 'kind', path), ELEMENT_KINDS, `${path}.kind`),
    id: str(raw, 'id', path),
    critical: bool(raw, 'critical', path),
    impact: parseFailureImpact(raw['impact'], `${path}.impact`),
    reasons:
      reasons === undefined
        ? []
        : strings(raw, 'reasons', path).map((reason, index) =>
            oneOf(reason, CRITICALITY_REASONS, `${path}.reasons[${String(index)}]`),
          ),
  };
}

function parseCriticalitySummary(value: unknown, path: string): CriticalitySummary {
  const raw = object(value, path);
  return {
    nodes_evaluated: num(raw, 'nodes_evaluated', path),
    links_evaluated: num(raw, 'links_evaluated', path),
    critical_nodes: num(raw, 'critical_nodes', path),
    critical_links: num(raw, 'critical_links', path),
  };
}

export function parseCriticalityResponse(
  value: unknown,
  path = 'CriticalityResponse',
): CriticalityResponse {
  const raw = object(value, path);
  return {
    assessments: items(raw, 'assessments', path, parseAssessment),
    summary: parseCriticalitySummary(raw['summary'], `${path}.summary`),
  };
}
