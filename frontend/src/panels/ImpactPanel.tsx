import type { JSX } from 'react';

import type { RankedLink, ScenarioReport, StrandedDemand } from '../api/types';
import type { FailureSet } from '../state/failedSet';
import { isNothingFailed, matchesReport } from '../state/failedSet';
import { useFailures } from '../state/failureContext';
import { PanelSection } from './PanelSection';

/** `1.0` is exactly full, per docs/api-contract.md's conventions; shown to one decimal. */
function asPercent(utilization: number): string {
  return `${(utilization * 100).toFixed(1)}%`;
}

/** A failed set in words, for captions and the failed list. Empty reads as "nothing". */
function describeSet(nodes: readonly string[], links: readonly string[]): string {
  const parts: string[] = [];
  if (nodes.length > 0) parts.push(`nodes ${nodes.join(', ')}`);
  if (links.length > 0) parts.push(`links ${links.join(', ')}`);
  return parts.length === 0 ? 'nothing' : parts.join('; ');
}

function FailedList({ failed }: { failed: FailureSet }): JSX.Element {
  const { restore, restoreAll } = useFailures();
  const total = failed.failedNodes.length + failed.failedLinks.length;
  return (
    <section className="impact-block" aria-labelledby="impact-failed-heading">
      <h3 id="impact-failed-heading" className="impact-heading">
        Failed now
      </h3>
      {total === 0 ? (
        <p className="panel-empty">Nothing has failed.</p>
      ) : (
        <>
          <ul className="failed-list">
            {failed.failedNodes.map((id) => (
              <li key={`node-${id}`}>
                <span>Node {id}</span>
                <button
                  type="button"
                  onClick={() => {
                    restore({ kind: 'node', id });
                  }}
                >
                  Restore {id}
                </button>
              </li>
            ))}
            {failed.failedLinks.map((id) => (
              <li key={`link-${id}`}>
                <span>Link {id}</span>
                <button
                  type="button"
                  onClick={() => {
                    restore({ kind: 'link', id });
                  }}
                >
                  Restore {id}
                </button>
              </li>
            ))}
          </ul>
          <button type="button" className="restore-all" onClick={restoreAll}>
            Restore everything
          </button>
        </>
      )}
    </section>
  );
}

function RankedTable({ links }: { links: readonly RankedLink[] }): JSX.Element {
  return (
    <table className="impact-table">
      <thead>
        <tr>
          <th scope="col">Link</th>
          <th scope="col">Utilization</th>
          <th scope="col">Load / capacity</th>
        </tr>
      </thead>
      <tbody>
        {links.map((ranked) => (
          <tr key={ranked.link_id}>
            <td>{ranked.link_id}</td>
            <td>{asPercent(ranked.utilization)}</td>
            <td>
              {ranked.load.toLocaleString()} / {ranked.capacity.toLocaleString()}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function DemandTable({ demands }: { demands: readonly StrandedDemand[] }): JSX.Element {
  return (
    <table className="impact-table">
      <thead>
        <tr>
          <th scope="col">Demand</th>
          <th scope="col">Endpoints</th>
          <th scope="col">Units</th>
        </tr>
      </thead>
      <tbody>
        {demands.map((demand) => (
          <tr key={demand.id}>
            <td>{demand.id}</td>
            <td>{demand.endpoints.join(', ')}</td>
            <td>{demand.volume.toLocaleString()}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The R8 result for the failed set. The two demand groups are separate sections with their
 * own headings and their own explanation, so a reader can tell them apart without relying
 * on colour. Nothing is rendered as an empty table: a group with no members says so in words.
 */
function Result({
  report,
  matches,
}: {
  report: ScenarioReport;
  matches: boolean;
}): JSX.Element {
  const reported = report.failed;
  const components = report.components;
  return (
    <>
      <p className="impact-caption">
        Result for {describeSet(reported.nodes ?? [], reported.links ?? [])}.{' '}
        {report.partitioned
          ? `The surviving network is split into ${String(components)} pieces.`
          : 'The surviving network is still connected.'}
      </p>
      {matches ? null : (
        <p className="impact-stale">
          The failed set has changed since this result was computed. It is the last result
          that resolved.
        </p>
      )}

      <section className="impact-block" aria-labelledby="impact-undeliverable-heading">
        <h3 id="impact-undeliverable-heading" className="impact-heading">
          Undeliverable demands
        </h3>
        {report.undeliverable_demands.length === 0 ? (
          <p className="panel-empty">No demand is undeliverable.</p>
        ) : (
          <DemandTable demands={report.undeliverable_demands} />
        )}
      </section>

      <section className="impact-block" aria-labelledby="impact-endpoint-heading">
        <h3 id="impact-endpoint-heading" className="impact-heading">
          Demands that start or end at a failed node
        </h3>
        <p className="placeholder-note">
          Lost because their own endpoint has failed, not because the network cannot carry
          them. Reported apart from the undeliverable demands above.
        </p>
        {report.endpoint_affected_demands.length === 0 ? (
          <p className="panel-empty">No demand starts or ends at a failed node.</p>
        ) : (
          <DemandTable demands={report.endpoint_affected_demands} />
        )}
      </section>

      <section className="impact-block" aria-labelledby="impact-overloaded-heading">
        <h3 id="impact-overloaded-heading" className="impact-heading">
          Links above 100% utilization
        </h3>
        {report.overloaded_links.length === 0 ? (
          <p className="panel-empty">No link is above 100% utilization.</p>
        ) : (
          <RankedTable links={report.overloaded_links} />
        )}
      </section>

      <section className="impact-block" aria-labelledby="impact-totals-heading">
        <h3 id="impact-totals-heading" className="impact-heading">
          Totals
        </h3>
        <dl className="impact-totals">
          <div>
            <dt>Demands</dt>
            <dd>{report.totals.demands}</dd>
          </div>
          <div>
            <dt>Units</dt>
            <dd>{report.totals.units.toLocaleString()}</dd>
          </div>
          <div>
            <dt>Units delivered</dt>
            <dd>{report.totals.units_delivered.toLocaleString()}</dd>
          </div>
          <div>
            <dt>Units undeliverable</dt>
            <dd>{report.totals.units_undeliverable.toLocaleString()}</dd>
          </div>
          <div>
            <dt>Units endpoint-affected</dt>
            <dd>{report.totals.units_endpoint_affected.toLocaleString()}</dd>
          </div>
        </dl>
      </section>
    </>
  );
}

/**
 * The impact of the current failed set (R8, R11).
 *
 * The failed set is listed with a restore button for each element and one for everything.
 * The result below it is the latest scenario answer. If a change is still being computed,
 * or the last one was rejected, that is said here, in words, next to the figures.
 */
export function ImpactPanel({
  report,
  pending,
  error,
}: {
  report: ScenarioReport | null;
  /** True while a scenario request for the current set is in flight. */
  pending: boolean;
  /** The message from the most recent request, when it was rejected. */
  error: string | null;
}): JSX.Element {
  const { failed } = useFailures();
  const nothingFailed = isNothingFailed(failed);
  const matches = report !== null && matchesReport(failed, report.failed);

  let body: JSX.Element;
  if (report === null) {
    body = <p className="panel-empty">Loading the baseline result.</p>;
  } else if (nothingFailed && isNothingFailed(reportedSet(report))) {
    body = (
      <p className="panel-empty">
        Nothing has failed, so there is no impact to show. Select a node or a link, on the
        map or in the Critical or Top five panels, to see its effect here.
      </p>
    );
  } else {
    body = <Result report={report} matches={matches} />;
  }

  return (
    <PanelSection
      id="impact"
      title="Impact"
      lands="Each change posts the whole failed set to the scenario endpoint and shows the answer here (R8, R11)."
    >
      <FailedList failed={failed} />
      {error === null ? null : (
        <div className="impact-error" role="alert">
          <p>The result for the current failed set could not be computed: {error}</p>
          <p>
            The live back end answers any scenario. The fixture source answers only the
            empty failed set and the single node Berlin. The map and the failed set still
            work, so restore elements to return to a scenario the fixture covers.
          </p>
        </div>
      )}
      {pending ? (
        <p className="impact-pending" role="status">
          Computing the result for the current failed set.
        </p>
      ) : null}
      {body}
    </PanelSection>
  );
}

function reportedSet(report: ScenarioReport): FailureSet {
  return {
    failedNodes: report.failed.nodes ?? [],
    failedLinks: report.failed.links ?? [],
  };
}
