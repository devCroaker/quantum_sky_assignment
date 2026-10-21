import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Legend } from '../../map/Legend';

/**
 * D21 asks for a legend "since a reader should not have to infer what a dashed line
 * means". This checks the legend names every encoding the map actually draws: the
 * critical-node ring and warning marker, the critical-link dash, and the top-five rank
 * badge and heavier stroke.
 */
describe('Legend', () => {
  it('names every non-colour encoding in use', () => {
    render(<Legend />);
    const legend = screen.getByRole('note', { name: 'Map legend' });
    const text = legend.textContent;
    expect(text).toMatch(/ring/i);
    expect(text).toMatch(/warning/i);
    expect(text).toMatch(/dashed/i);
    expect(text).toMatch(/badge/i);
    expect(text).toMatch(/heavier stroke/i);
  });
});
