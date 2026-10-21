/**
 * GENERATED FILE. DO NOT EDIT BY HAND.
 *
 * Produced from contracts/schema.json by `npm run types`.
 * `npm run types:check` and src/test/generated-types.test.ts both fail when this
 * file no longer matches the schema. Change the Pydantic models and regenerate.
 */

/**
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "ElementKind".
 */
export type ElementKind = 'node' | 'link';
/**
 * Why an element is critical: the three ways losing it hurts someone else.
 *
 * R7 gives three reasons and these are they. An element is critical when its
 * loss partitions the network, strands a demand between two nodes that both
 * survive, or drives a surviving link over capacity.
 *
 * What is deliberately **not** here is a demand lost because its own endpoint
 * failed. That is reported, in ``FailureImpact.endpoint_affected_demands``
 * and as its own bucket in ``ScenarioReport``, because R8 requires it to be
 * reported separately. It just does not make an element critical.
 *
 * The project ran for a while with the opposite reading, under which a node
 * was critical if losing it stranded any demand at all, including its own.
 * That is the literal text of R7b, and it was tried. It marked 37 of the
 * real network's 37 nodes critical, because 36 of them originate traffic and
 * the thirty-seventh partitions the graph, so the flag could not be lower
 * whatever the network looked like and said nothing about its shape. The
 * panel reverted it. Criticality now means "losing this hurts somebody
 * else", which is the question an operations team was actually asking.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "CriticalityReason".
 */
export type CriticalityReason = 'partitions-network' | 'demands-undeliverable' | 'links-overloaded';
/**
 * Where a link came from, which decides how its capacity was set.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "LinkKind".
 */
export type LinkKind = 'backbone' | 'access';
/**
 * What a node is, which decides whether it may forward traffic.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "NodeKind".
 */
export type NodeKind = 'backbone-city' | 'data-center' | 'operations-site' | 'aggregation-hub';

export interface NetscopeAPIContract {
  [k: string]: unknown;
}
/**
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "Assessment".
 */
export interface Assessment {
  /**
   * True when at least one R7 reason applies
   */
  critical: boolean;
  id: string;
  impact: FailureImpact;
  kind: ElementKind;
  /**
   * Empty when the element is not critical
   */
  reasons?: CriticalityReason[];
}
/**
 * What measurably happens when one element is lost.
 *
 * Reported for every element, critical or not, so that the view can rank
 * links by how much traffic depends on them.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "FailureImpact".
 */
export interface FailureImpact {
  components: number;
  endpoint_affected_demands: number;
  endpoint_affected_units: number;
  /**
   * Highest utilization on any surviving link after this failure
   */
  max_utilization: number;
  overloaded_links: number;
  undeliverable_demands: number;
  undeliverable_units: number;
}
/**
 * GET /api/v1/criticality
 *
 * Every node and every link, each with its reasons and its impact. The
 * critical ones are those with a non-empty reason list.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "CriticalityResponse".
 */
export interface CriticalityResponse {
  assessments: Assessment[];
  summary: CriticalitySummary;
}
/**
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "CriticalitySummary".
 */
export interface CriticalitySummary {
  critical_links: number;
  critical_nodes: number;
  links_evaluated: number;
  nodes_evaluated: number;
}
/**
 * A rejected input or request, located the way R2 requires.
 *
 * The parts stay separate rather than being pre-formatted into a sentence,
 * so the view can show the file and row as its own field and link to them.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "ErrorDetail".
 */
export interface ErrorDetail {
  field?: string | null;
  file?: string | null;
  line?: number | null;
  message: string;
  row?: number | null;
}
/**
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "ErrorResponse".
 */
export interface ErrorResponse {
  error: ErrorDetail;
}
/**
 * Which elements are down. An empty set is the baseline.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "FailedSet".
 */
export interface FailedSet {
  links?: string[];
  nodes?: string[];
}
/**
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "LinkLoad".
 */
export interface LinkLoad {
  capacity: number;
  link_id: string;
  /**
   * Demand units carried, summed over all demands
   */
  load: number;
  /**
   * load divided by capacity. 1.0 is exactly full
   */
  utilization: number;
}
/**
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "LinkWire".
 */
export interface LinkWire {
  capacity: number;
  /**
   * The two node ids, sorted. Links have no direction, per R3.
   *
   * @minItems 2
   * @maxItems 2
   */
  endpoints: [string, string];
  id: string;
  kind: LinkKind;
}
/**
 * GET /api/v1/network
 *
 * The topology and nothing derived from it. The 391 individual demands are
 * deliberately not included: the view never lists them all, and the ones it
 * does show arrive with full detail in a scenario report.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "NetworkResponse".
 */
export interface NetworkResponse {
  links: LinkWire[];
  nodes: NodeWire[];
  totals: NetworkTotals;
}
/**
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "NodeWire".
 */
export interface NodeWire {
  /**
   * For a site from sites.csv, the node ids it attaches to. Empty for a backbone city. Present so the view can show R9's 'near what it attaches to' relationship.
   */
  attaches_to?: string[];
  /**
   * R6: whether this node may forward traffic for other nodes
   */
  can_transit: boolean;
  id: string;
  kind: NodeKind;
  position: Position;
}
/**
 * A node's position on the map.
 *
 * SNDlib names these x and y. x is longitude and y is latitude, and the
 * names are kept so the payload reads like the source data.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "Position".
 */
export interface Position {
  /**
   * Longitude in degrees
   */
  x: number;
  /**
   * Latitude in degrees
   */
  y: number;
}
/**
 * The R1 acceptance figures, served so the view can display them.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "NetworkTotals".
 */
export interface NetworkTotals {
  demand_units: number;
  demands: number;
  links: number;
  nodes: number;
}
/**
 * A link load carrying its position in an ordered list.
 *
 * The rank is computed server side so that the view and any table or export
 * agree on the order, including how ties were broken.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "RankedLink".
 */
export interface RankedLink {
  capacity: number;
  link_id: string;
  /**
   * Demand units carried, summed over all demands
   */
  load: number;
  rank: number;
  /**
   * load divided by capacity. 1.0 is exactly full
   */
  utilization: number;
}
/**
 * The R8 answer: what breaks when these elements are down.
 *
 * Also the baseline response, with an empty ``failed`` set.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "ScenarioReport".
 */
export interface ScenarioReport {
  /**
   * Number of connected components among surviving nodes
   */
  components: number;
  /**
   * R8 requires these be reported separately: demands that start or end at a failed node, which are lost because their own endpoint is gone rather than because the network could not carry them.
   */
  endpoint_affected_demands: StrandedDemand[];
  failed: FailedSet;
  /**
   * Every surviving link, so the view can shade the whole map
   */
  link_loads: LinkLoad[];
  /**
   * R10: the five most utilized links, ranked
   */
  most_utilized: RankedLink[];
  /**
   * R8: every link above 100% utilization, worst first
   */
  overloaded_links: RankedLink[];
  /**
   * R7a: whether the surviving graph is in more than one piece
   */
  partitioned: boolean;
  totals: ScenarioTotals;
  /**
   * R8: demands with no remaining path, excluding the bucket below
   */
  undeliverable_demands: StrandedDemand[];
}
/**
 * A demand that cannot be delivered in this scenario.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "StrandedDemand".
 */
export interface StrandedDemand {
  /**
   * @minItems 2
   * @maxItems 2
   */
  endpoints: [string, string];
  id: string;
  volume: number;
}
/**
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "ScenarioTotals".
 */
export interface ScenarioTotals {
  demands: number;
  units: number;
  units_delivered: number;
  units_endpoint_affected: number;
  units_undeliverable: number;
}
/**
 * POST /api/v1/scenario
 *
 * R7 and R8 only ask about a single failed element. This accepts a set
 * because a set is a superset of that case, it costs nothing, and it lets
 * the view model "fail these two and see" without a contract change.
 *
 * This interface was referenced by `NetscopeAPIContract`'s JSON-Schema
 * via the `definition` "ScenarioRequest".
 */
export interface ScenarioRequest {
  failed_links?: string[];
  failed_nodes?: string[];
}
