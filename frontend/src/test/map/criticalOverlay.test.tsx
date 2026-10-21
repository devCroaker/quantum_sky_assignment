import baselineFixture from '@contracts/fixtures/baseline.json';
import criticalityFixture from '@contracts/fixtures/criticality.json';
import networkFixture from '@contracts/fixtures/network.json';
import { render } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import {
  parseCriticalityResponse,
  parseNetworkResponse,
  parseScenarioReport,
} from '../../api/guards';
import { MapView } from '../../map/MapView';
import { SelectionProvider } from '../../state/selection';

const network = parseNetworkResponse(networkFixture);
const criticality = parseCriticalityResponse(criticalityFixture);
const baseline = parseScenarioReport(baselineFixture);

function renderMap(): ReturnType<typeof render> {
  return render(
    <SelectionProvider>
      <MapView
        network={network}
        criticality={criticality}
        mostUtilized={baseline.most_utilized}
      />
    </SelectionProvider>,
  );
}

/**
 * D21's enforcement test: every element the Critical panel and the map agree is critical
 * must carry a non-colour DOM attribute saying why, and every one of the five most utilized
 * links must carry its rank the same way. This is what lets a test (rather than a human
 * squinting at a greyscale screenshot) prove the encoding is really there.
 */
describe('MapView critical and top-five overlays (D21)', () => {
  it('matches the fixture-derived counts: 6 of 7 nodes and 3 of 8 links critical', () => {
    // Derived from the fixture's own summary, never hardcoded independently of it, per
    // CLAUDE.md's "never invent a number": this is the number the server computed, and the
    // test holds the view to reproducing it, not to agreeing with itself.
    const criticalNodeCount = criticality.assessments.filter(
      (a) => a.kind === 'node' && a.critical,
    ).length;
    const criticalLinkCount = criticality.assessments.filter(
      (a) => a.kind === 'link' && a.critical,
    ).length;
    expect(criticalNodeCount).toBe(criticality.summary.critical_nodes);
    expect(criticalLinkCount).toBe(criticality.summary.critical_links);
    expect(criticalNodeCount).toBe(6);
    expect(criticalLinkCount).toBe(3);
  });

  it('gives every critical node a data-critical-reasons attribute naming its reasons', () => {
    const { container } = renderMap();
    for (const assessment of criticality.assessments) {
      if (assessment.kind !== 'node') continue;
      const glyph = container.querySelector(`[data-node-id="${assessment.id}"]`);
      expect(glyph).not.toBeNull();
      if (assessment.critical) {
        const reasonsAttr = glyph?.getAttribute('data-critical-reasons');
        expect(reasonsAttr).toBeTruthy();
        for (const reason of assessment.reasons ?? []) {
          expect(reasonsAttr).toContain(reason);
        }
        // The visible ring and warning marker, not only the attribute: D21 asks for both.
        expect(glyph?.querySelector('.critical-ring')).not.toBeNull();
        expect(glyph?.querySelector('.critical-marker')).not.toBeNull();
      } else {
        expect(glyph?.hasAttribute('data-critical-reasons')).toBe(false);
        expect(glyph?.querySelector('.critical-ring')).toBeNull();
      }
    }
  });

  it('gives every critical link a data-critical-reasons attribute naming its reasons', () => {
    const { container } = renderMap();
    for (const assessment of criticality.assessments) {
      if (assessment.kind !== 'link') continue;
      const line = container.querySelector(`[data-link-id="${assessment.id}"]`);
      expect(line).not.toBeNull();
      if (assessment.critical) {
        const reasonsAttr = line?.getAttribute('data-critical-reasons');
        expect(reasonsAttr).toBeTruthy();
        for (const reason of assessment.reasons ?? []) {
          expect(reasonsAttr).toContain(reason);
        }
        expect(line?.classList.contains('link-critical')).toBe(true);
      } else {
        expect(line?.hasAttribute('data-critical-reasons')).toBe(false);
        expect(line?.classList.contains('link-critical')).toBe(false);
      }
    }
  });

  it('gives every one of the five most utilized links a data-rank attribute and a visible badge', () => {
    const { container } = renderMap();
    expect(baseline.most_utilized).toHaveLength(5);
    for (const ranked of baseline.most_utilized) {
      const line = container.querySelector(`[data-link-id="${ranked.link_id}"]`);
      expect(line).not.toBeNull();
      expect(line?.getAttribute('data-rank')).toBe(String(ranked.rank));
      expect(line?.classList.contains('link-top-utilized')).toBe(true);
    }
    // The numeral itself, visible, is the actual non-colour encoding; the attribute is
    // what lets this test check for it without reading pixels. Scoped to the map's own
    // <svg>, since the legend below it draws its own demonstration rank badge with the
    // same class.
    const mapSvg = container.querySelector('svg.map-svg');
    const badgeNumbers = Array.from(
      mapSvg?.querySelectorAll('.rank-badge text') ?? [],
    ).map((el) => el.textContent);
    expect(badgeNumbers.sort()).toEqual(['1', '2', '3', '4', '5']);
  });

  it('draws both overlays on a link that is both critical and top-five, per the fixture', () => {
    // On this fixture the three critical links (the small-capacity access links and L4)
    // are also exactly the three most utilized: a small access link needs little load to
    // reach a high percentage. ACC-HUB-EAST-Warsaw is both critical and rank 4, so both
    // attributes, and both classes, must be present at once rather than one overlay
    // silently winning.
    const { container } = renderMap();
    const line = container.querySelector('[data-link-id="ACC-HUB-EAST-Warsaw"]');
    expect(line?.getAttribute('data-critical-reasons')).toBeTruthy();
    expect(line?.getAttribute('data-rank')).toBe('4');
    expect(line?.classList.contains('link-critical')).toBe(true);
    expect(line?.classList.contains('link-top-utilized')).toBe(true);
  });
});
