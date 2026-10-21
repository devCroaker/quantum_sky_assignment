import berlinDownFixture from '@contracts/fixtures/scenario-berlin-down.json';
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import type { Mock } from 'vitest';
import { describe, expect, it, vi } from 'vitest';

import type { NetworkDataSource } from '../../api';
import { createFixtureDataSource } from '../../api/fixtureDataSource';
import { parseScenarioReport } from '../../api/guards';
import type { ScenarioReport, ScenarioRequest } from '../../api/types';
import { App } from '../../app/App';

/**
 * Fail and restore, end to end through the App, against the fixture source where it can
 * answer and against scripted sources where a test needs control over the answer.
 *
 * The fixture answers the empty set and Berlin only. Berlin's answer is the committed
 * scenario-berlin-down.json, so its figures are the hand-worked ones documented there.
 */

const fixture = createFixtureDataSource();
const berlinReport = parseScenarioReport(berlinDownFixture);

/** A fixture source whose scenario calls are recorded, so a test can read what was posted. */
function recordingSource(): {
  source: NetworkDataSource;
  scenario: Mock<(request: ScenarioRequest) => Promise<ScenarioReport>>;
} {
  const scenario = vi.fn<(request: ScenarioRequest) => Promise<ScenarioReport>>(
    (request) => fixture.scenario(request),
  );
  return { source: { ...fixture, scenario }, scenario };
}

function glyph(container: HTMLElement, id: string): HTMLElement {
  const element = container.querySelector<HTMLElement>(`[data-node-id="${id}"]`);
  if (element === null) throw new Error(`no node glyph for ${id}`);
  return element;
}

/** The panel section a heading belongs to, so assertions read inside one group only. */
function sectionOf(heading: HTMLElement): HTMLElement {
  const section = heading.closest<HTMLElement>('section');
  if (section === null) throw new Error('heading is not inside a section');
  return section;
}

function impactPanel(): HTMLElement {
  return sectionOf(screen.getByRole('heading', { name: 'Impact', level: 2 }));
}

/** A report for an arbitrary failed set, derived from the Berlin answer for tests that need one. */
function reportFor(nodes: string[]): ScenarioReport {
  return { ...berlinReport, failed: { nodes, links: [] } };
}

describe('failing and restoring an element', () => {
  it('posts the failed set when Berlin fails, and the Impact panel renders that response', async () => {
    const { source, scenario } = recordingSource();
    const { container } = render(<App source={source} />);

    fireEvent.click(await waitForGlyph(container, 'Berlin'));

    await waitFor(() => {
      expect(scenario).toHaveBeenLastCalledWith({
        failed_nodes: ['Berlin'],
        failed_links: [],
      });
    });

    const impact = impactPanel();
    // Berlin's committed answer strands two demands, D1 and D2, and 110 units in total.
    const undeliverable = sectionOf(
      within(impact).getByRole('heading', { name: 'Undeliverable demands', level: 3 }),
    );
    expect(within(undeliverable).getByText('D1')).toBeTruthy();
    expect(within(undeliverable).getByText('D2')).toBeTruthy();
    expect(
      within(impact).getByText('Units undeliverable').parentElement?.textContent,
    ).toBe('Units undeliverable110');
    expect(within(impact).getByText('Node Berlin')).toBeTruthy();
  });

  it('restores everything by posting two empty arrays', async () => {
    const { source, scenario } = recordingSource();
    const { container } = render(<App source={source} />);

    fireEvent.click(await waitForGlyph(container, 'Berlin'));
    await waitFor(() => {
      expect(scenario).toHaveBeenCalledTimes(1);
    });

    fireEvent.click(screen.getByRole('button', { name: 'Restore everything' }));

    await waitFor(() => {
      expect(scenario).toHaveBeenLastCalledWith({ failed_nodes: [], failed_links: [] });
    });
    expect(within(impactPanel()).getByText('Nothing has failed.')).toBeTruthy();
    expect(glyph(container, 'Berlin').hasAttribute('data-failed')).toBe(false);
  });

  it('restores one element from the failed list and leaves the others failed', async () => {
    const { source, scenario } = recordingSource();
    const { container } = render(<App source={source} />);

    // Hamburg is outside the fixture's two answers, so this pair is rejected. The restore
    // of Hamburg is what the test is about: it must post Berlin alone, which the fixture
    // does answer.
    fireEvent.click(await waitForGlyph(container, 'Berlin'));
    fireEvent.click(glyph(container, 'Hamburg'));
    await waitFor(() => {
      expect(scenario).toHaveBeenLastCalledWith({
        failed_nodes: ['Berlin', 'Hamburg'],
        failed_links: [],
      });
    });

    fireEvent.click(screen.getByRole('button', { name: 'Restore Hamburg' }));
    await waitFor(() => {
      expect(scenario).toHaveBeenLastCalledWith({
        failed_nodes: ['Berlin'],
        failed_links: [],
      });
    });
    expect(glyph(container, 'Hamburg').hasAttribute('data-failed')).toBe(false);
    expect(glyph(container, 'Berlin').getAttribute('data-failed')).toBe('true');
  });
});

describe('the R8 result', () => {
  it('reports undeliverable and endpoint-affected demands under separate headings', async () => {
    // The Berlin fixture has no endpoint-affected demand, so one is added here to exercise
    // the grouping. D9 is invented for this test only; the undeliverable D1 and D2 are the
    // committed Berlin answer.
    const withEndpointDemand: ScenarioReport = {
      ...berlinReport,
      endpoint_affected_demands: [
        { id: 'D9', endpoints: ['Berlin', 'DC-NORTH'], volume: 40 },
      ],
    };
    const source: NetworkDataSource = {
      ...fixture,
      scenario: (request) =>
        request.failed_nodes?.includes('Berlin') === true
          ? Promise.resolve(withEndpointDemand)
          : fixture.scenario(request),
    };
    const { container } = render(<App source={source} />);
    fireEvent.click(await waitForGlyph(container, 'Berlin'));

    const impact = impactPanel();
    const undeliverableHeading = await within(impact).findByRole('heading', {
      name: 'Undeliverable demands',
      level: 3,
    });
    const endpointHeading = within(impact).getByRole('heading', {
      name: 'Demands that start or end at a failed node',
      level: 3,
    });
    expect(undeliverableHeading).not.toBe(endpointHeading);

    const undeliverable = sectionOf(undeliverableHeading);
    const endpoint = sectionOf(endpointHeading);
    expect(undeliverable).not.toBe(endpoint);
    expect(within(undeliverable).getByText('D1')).toBeTruthy();
    expect(within(undeliverable).queryByText('D9')).toBeNull();
    expect(within(endpoint).getByText('D9')).toBeTruthy();
    expect(within(endpoint).queryByText('D1')).toBeNull();
  });

  it('says in words that nothing has failed, with no empty tables', async () => {
    render(<App source={fixture} />);
    const impact = impactPanel();
    // The baseline arrives asynchronously, so the sentence appears once it has.
    expect(
      await within(impact).findByText(
        /Nothing has failed, so there is no impact to show/,
      ),
    ).toBeTruthy();
    expect(impact.querySelector('table')).toBeNull();
  });
});

describe('the encoding of a failed element', () => {
  it('marks a failed element data-failed="true" and leaves a critical one without it', async () => {
    const { container } = render(<App source={fixture} />);

    // Berlin is critical in the criticality fixture and is about to fail, so it carries both.
    fireEvent.click(await waitForGlyph(container, 'Berlin'));
    await waitFor(() => {
      expect(glyph(container, 'Berlin').getAttribute('data-failed')).toBe('true');
    });
    expect(glyph(container, 'Berlin').getAttribute('data-critical-reasons')).not.toBe('');

    // Warsaw is critical and has not failed: it must look critical and not failed.
    const warsaw = glyph(container, 'Warsaw');
    expect(warsaw.getAttribute('data-critical-reasons')).not.toBe(null);
    expect(warsaw.hasAttribute('data-failed')).toBe(false);
    expect(warsaw.querySelector('.critical-ring')).not.toBeNull();
    expect(warsaw.querySelector('.failed-marker')).toBeNull();
  });
});

describe('the keyboard', () => {
  it('toggles a focused node on Enter and on Space', async () => {
    const { source, scenario } = recordingSource();
    const { container } = render(<App source={source} />);
    const berlin = await waitForGlyph(container, 'Berlin');

    fireEvent.keyDown(berlin, { key: 'Enter' });
    await waitFor(() => {
      expect(scenario).toHaveBeenLastCalledWith({
        failed_nodes: ['Berlin'],
        failed_links: [],
      });
    });

    fireEvent.keyDown(berlin, { key: ' ' });
    await waitFor(() => {
      expect(scenario).toHaveBeenLastCalledWith({ failed_nodes: [], failed_links: [] });
    });
  });

  it('toggles a focused link on Enter, which a pointer alone used to be the only way to reach', async () => {
    const { source, scenario } = recordingSource();
    const { container } = render(<App source={source} />);
    await waitForGlyph(container, 'Berlin');

    const link = container.querySelector<HTMLElement>('line[data-link-id]');
    const linkId = link?.getAttribute('data-link-id');
    if (link === null || linkId === undefined || linkId === null) {
      throw new Error('the fixture has no link');
    }
    fireEvent.keyDown(link, { key: 'Enter' });
    await waitFor(() => {
      expect(scenario).toHaveBeenLastCalledWith({
        failed_nodes: [],
        failed_links: [linkId],
      });
    });
  });
});

describe('an unsupported fixture scenario', () => {
  it('shows the rejection, keeps the map drawn, and lets the failed set be restored', async () => {
    const { container } = render(<App source={fixture} />);

    fireEvent.click(await waitForGlyph(container, 'Hamburg'));

    const alert = await screen.findByRole('alert');
    expect(alert.textContent).toMatch(/not available in fixture mode/);
    expect(alert.textContent).toMatch(/live back end answers any scenario/);

    // The map is still there, with every fixture node on it.
    expect(screen.getByRole('application')).toBeTruthy();
    expect(container.querySelectorAll('.node-glyph')).toHaveLength(7);

    // Restoring returns the fixture to a scenario it covers, and the rejection goes with it.
    fireEvent.click(screen.getByRole('button', { name: 'Restore Hamburg' }));
    await waitFor(() => {
      expect(screen.queryByRole('alert')).toBeNull();
    });
  });
});

describe('out-of-order responses', () => {
  it('shows the newer answer even when the older one resolves last', async () => {
    const queued: {
      request: ScenarioRequest;
      resolve: (report: ScenarioReport) => void;
    }[] = [];
    const source: NetworkDataSource = {
      ...fixture,
      scenario: (request) =>
        new Promise<ScenarioReport>((resolve) => {
          queued.push({ request, resolve });
        }),
    };
    const { container } = render(<App source={source} />);
    await waitForGlyph(container, 'Berlin');

    fireEvent.click(glyph(container, 'Berlin'));
    fireEvent.click(glyph(container, 'Warsaw'));
    await waitFor(() => {
      expect(queued).toHaveLength(2);
    });
    const [older, newer] = queued;
    if (older === undefined || newer === undefined)
      throw new Error('two requests expected');

    await act(async () => {
      newer.resolve(reportFor(['Berlin', 'Warsaw']));
      await settle();
    });
    expect(
      await within(impactPanel()).findByText(/Result for nodes Berlin, Warsaw/),
    ).toBeTruthy();

    // The older answer arrives last. It must not replace the newer one on screen.
    await act(async () => {
      older.resolve(reportFor(['Berlin']));
      await settle();
    });
    expect(
      within(impactPanel()).getByText(/Result for nodes Berlin, Warsaw/),
    ).toBeTruthy();
    expect(within(impactPanel()).queryByText(/Result for nodes Berlin\./)).toBeNull();
  });
});

/**
 * Lets already-resolved promise callbacks run. The App applies a response in a `.then`, one
 * microtask after the test resolves it, so a macrotask boundary is enough to see its effect.
 */
function settle(): Promise<void> {
  return new Promise((resolve) => {
    setTimeout(resolve, 0);
  });
}

/** Waits for the map to draw a node, since the network arrives asynchronously. */
async function waitForGlyph(container: HTMLElement, id: string): Promise<HTMLElement> {
  await waitFor(() => {
    expect(container.querySelector(`[data-node-id="${id}"]`)).not.toBeNull();
  });
  return glyph(container, id);
}
