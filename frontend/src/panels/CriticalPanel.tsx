import type { JSX } from 'react';
import { useMemo, useState } from 'react';

import type { Assessment, CriticalityReason, CriticalityResponse } from '../api/types';
import { useFailureToggle } from '../state/failureContext';
import { useHighlightHandlers } from '../state/selectionContext';
import {
  countsByReason,
  DEFAULT_REASONS,
  matchesReasonFilter,
  REASON_LABEL,
  REASONS,
} from './criticalFilter';
import { PanelSection } from './PanelSection';

function Row({ assessment }: { assessment: Assessment }): JSX.Element {
  const { highlighted, onPointerEnter, onPointerLeave, onFocus, onBlur, onSelect } =
    useHighlightHandlers({ kind: assessment.kind, id: assessment.id });
  // A native button turns Enter and Space into a click, so the click handler alone covers
  // the keyboard as well as the pointer (R11).
  const { failed, toggle } = useFailureToggle({
    kind: assessment.kind,
    id: assessment.id,
  });
  const reasons = assessment.reasons ?? [];
  return (
    <li>
      <button
        type="button"
        className={`critical-row${highlighted ? ' is-highlighted' : ''}${failed ? ' is-failed' : ''}`}
        data-critical-reasons={reasons.join(' ')}
        data-failed={failed ? 'true' : undefined}
        aria-pressed={failed}
        onMouseEnter={onPointerEnter}
        onMouseLeave={onPointerLeave}
        onFocus={onFocus}
        onBlur={onBlur}
        onClick={() => {
          onSelect();
          toggle();
        }}
      >
        <span className="critical-row-id">{assessment.id}</span>
        <span className="critical-row-kind">{assessment.kind}</span>
        <span className="critical-row-reasons">
          {reasons.map((reason) => REASON_LABEL[reason]).join('; ')}
        </span>
        {failed ? <span className="failed-tag">Failed: activate to restore</span> : null}
      </button>
    </li>
  );
}

/**
 * Critical elements (R10), grouped by why rather than listed flat.
 *
 * On the real network 6 of the 37 nodes are critical, and 6 of the 55 links
 * (docs/api-contract.md, decision 3b), because file A is a full mesh and every site
 * originates a demand: a flat list of 36 names is not a useful answer to "where are the
 * single points of failure". Filtering to the structural reasons, `partitions-network` and
 * `demands-undeliverable`, is what gets back to the short list an operations lead actually
 * wants, so that is the default here (see ./criticalFilter.ts); every reason remains one
 * checkbox away, with its own count, for the reader who wants the literal flag instead.
 */
export function CriticalPanel({
  criticality,
}: {
  criticality: CriticalityResponse;
}): JSX.Element {
  const [selected, setSelected] =
    useState<ReadonlySet<CriticalityReason>>(DEFAULT_REASONS);

  const counts = useMemo(
    () => countsByReason(criticality.assessments),
    [criticality.assessments],
  );
  const critical = useMemo(
    () => criticality.assessments.filter((assessment) => assessment.critical),
    [criticality.assessments],
  );
  const filtered = useMemo(
    () => critical.filter((assessment) => matchesReasonFilter(assessment, selected)),
    [critical, selected],
  );

  function toggle(reason: CriticalityReason): void {
    setSelected((previous) => {
      const next = new Set(previous);
      if (next.has(reason)) next.delete(reason);
      else next.add(reason);
      return next;
    });
  }

  const { summary } = criticality;

  return (
    <PanelSection
      id="critical"
      title="Critical"
      lands={`${String(summary.critical_nodes)} of ${String(summary.nodes_evaluated)} nodes and ${String(summary.critical_links)} of ${String(summary.links_evaluated)} links are critical under R7, meaning their loss costs somebody else something. Narrow by reason below.`}
    >
      <fieldset className="critical-filter">
        <legend>Show reasons</legend>
        {REASONS.map((reason) => (
          <label key={reason} className="critical-filter-option">
            <input
              type="checkbox"
              checked={selected.has(reason)}
              onChange={() => {
                toggle(reason);
              }}
            />
            {REASON_LABEL[reason]} ({counts[reason]})
          </label>
        ))}
      </fieldset>
      <p className="critical-filter-count">
        Showing {filtered.length} of {critical.length} critical elements
      </p>
      {filtered.length === 0 ? (
        <p className="panel-empty">No critical element matches the selected reasons.</p>
      ) : (
        <ul className="critical-list">
          {filtered.map((assessment) => (
            <Row key={`${assessment.kind}-${assessment.id}`} assessment={assessment} />
          ))}
        </ul>
      )}
    </PanelSection>
  );
}
