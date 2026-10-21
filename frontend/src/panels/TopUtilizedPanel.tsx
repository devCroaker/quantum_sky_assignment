import type { JSX } from 'react';

import type { NetworkResponse, RankedLink, ScenarioReport } from '../api/types';
import { useFailureToggle } from '../state/failureContext';
import { useHighlightHandlers } from '../state/selectionContext';
import { PanelSection } from './PanelSection';

/** `1.0` is exactly full, per docs/api-contract.md's conventions; shown to one decimal. */
function asPercent(utilization: number): string {
  return `${(utilization * 100).toFixed(1)}%`;
}

function endpointsOf(
  network: NetworkResponse,
  linkId: string,
): readonly [string, string] | undefined {
  return network.links.find((link) => link.id === linkId)?.endpoints;
}

function Row({
  ranked,
  endpoints,
}: {
  ranked: RankedLink;
  endpoints: readonly [string, string] | undefined;
}): JSX.Element {
  const { highlighted, onPointerEnter, onPointerLeave, onFocus, onBlur, onSelect } =
    useHighlightHandlers({ kind: 'link', id: ranked.link_id });
  const { failed, toggle, onKeyDown } = useFailureToggle({
    kind: 'link',
    id: ranked.link_id,
  });
  return (
    <tr
      className={highlighted ? 'is-highlighted' : undefined}
      data-rank={ranked.rank}
      data-failed={failed ? 'true' : undefined}
      tabIndex={0}
      onMouseEnter={onPointerEnter}
      onMouseLeave={onPointerLeave}
      onFocus={onFocus}
      onBlur={onBlur}
      onClick={() => {
        onSelect();
        toggle();
      }}
      onKeyDown={onKeyDown}
    >
      <td className="top-utilized-rank">{ranked.rank}</td>
      <td>
        {ranked.link_id}
        {failed ? <span className="failed-tag"> failed</span> : null}
      </td>
      <td>{endpoints !== undefined ? endpoints.join(' – ') : 'unknown'}</td>
      {/*
        Read straight off the payload, never recomputed: docs/api-contract.md's conventions
        say utilization is load over capacity, but dividing it back out here would let the
        view and the server quietly disagree if the server's rounding ever changed.
      */}
      <td>{asPercent(ranked.utilization)}</td>
      <td>
        {ranked.load.toLocaleString()} / {ranked.capacity.toLocaleString()}
      </td>
    </tr>
  );
}

/**
 * The five most utilized links (R10), in the order `ScenarioReport.most_utilized` already
 * carries (D4: ranked server side, ties broken on link id). This view only looks the rank
 * up; it never re-sorts the list or re-derives utilization from load and capacity, so it
 * cannot disagree with the server, the map's rank badges, or a future export about which
 * five links they are or in what order.
 */
export function TopUtilizedPanel({
  report,
  network,
}: {
  report: ScenarioReport;
  network: NetworkResponse;
}): JSX.Element {
  return (
    <PanelSection
      id="top-utilized"
      title="Top five utilized"
      lands="The five most utilized links, ranked by the server. Rank and utilization are shown exactly as returned, never recomputed here."
    >
      {report.most_utilized.length === 0 ? (
        <p className="panel-empty">No links carry any load in this scenario.</p>
      ) : (
        <table className="top-utilized-table">
          <thead>
            <tr>
              <th scope="col">Rank</th>
              <th scope="col">Link</th>
              <th scope="col">Endpoints</th>
              <th scope="col">Utilization</th>
              <th scope="col">Load / capacity</th>
            </tr>
          </thead>
          <tbody>
            {report.most_utilized.map((ranked) => (
              <Row
                key={ranked.link_id}
                ranked={ranked}
                endpoints={endpointsOf(network, ranked.link_id)}
              />
            ))}
          </tbody>
        </table>
      )}
    </PanelSection>
  );
}
