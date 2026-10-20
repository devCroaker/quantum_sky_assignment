import type { JSX, ReactNode } from 'react';

/**
 * One section of the persistent side panel.
 *
 * The three sections share a frame so that P17 and P18 only have to supply a body, and so
 * the heading levels and labelling stay consistent as they are filled in.
 */
export function PanelSection({
  id,
  title,
  lands,
  children,
}: {
  id: string;
  title: string;
  /** Which task and requirement fill this section, shown so the state is never unclear. */
  lands: string;
  children: ReactNode;
}): JSX.Element {
  const headingId = `${id}-heading`;
  return (
    <section className="panel-section" aria-labelledby={headingId}>
      <h2 id={headingId} className="panel-section-title">
        {title}
      </h2>
      <p className="placeholder-note">{lands}</p>
      {children}
    </section>
  );
}
