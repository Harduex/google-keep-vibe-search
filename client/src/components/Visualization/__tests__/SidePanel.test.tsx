import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SidePanel, SidePanelProps } from '../SidePanel';

const baseProps: SidePanelProps = {
  selected: null,
  chainTitles: [],
  connections: null,
  connectionsError: null,
  connectionsLoading: false,
  layers: { similar: true, tags: false, entities: false },
  onToggleLayer: vi.fn(),
  legend: [{ label: 'Recipes', color: '#0072b2' }],
  isolatedTag: null,
  onIsolateTag: vi.fn(),
  allTags: ['Recipes', 'Travel'],
  ghost: false,
  canGhost: true,
  onToggleGhost: vi.fn(),
  hideUnfocused: false,
  onToggleHideUnfocused: vi.fn(),
  onOpenNote: vi.fn(),
  onClearPath: vi.fn(),
};

const selectedProps: SidePanelProps = {
  ...baseProps,
  selected: {
    id: 'n1',
    title: 'My note',
    snippet: 'hello',
    tags: ['Recipes'],
    coordinates: [0, 0, 0],
  },
  chainTitles: ['My note'],
  connections: {
    id: 'n1',
    similar: [{ id: 'n2', title: 'Two', score: 0.9 }],
    shared_tags: [{ tag: 'Recipes', notes: [{ id: 'n3', title: 'Three' }] }],
    shared_entities: [],
  },
};

describe('SidePanel', () => {
  it('shows the selected note and per-layer counts', () => {
    render(<SidePanel {...selectedProps} />);
    expect(screen.getByText('My note')).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /similar.*1/i })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /shared tags.*1/i })).toBeTruthy();
    expect(screen.getByRole('checkbox', { name: /shared entities.*0/i })).toBeTruthy();
  });

  it('toggles layers and opens the note', () => {
    render(<SidePanel {...selectedProps} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /shared tags/i }));
    expect(selectedProps.onToggleLayer).toHaveBeenCalledWith('tags');
    fireEvent.click(screen.getByRole('button', { name: /open note/i }));
    expect(selectedProps.onOpenNote).toHaveBeenCalledWith('n1');
  });

  it('isolates a tag from the legend and clears it on second click', () => {
    const onIsolateTag = vi.fn();
    const { rerender } = render(<SidePanel {...baseProps} onIsolateTag={onIsolateTag} />);
    fireEvent.click(screen.getByRole('button', { name: 'Recipes' }));
    expect(onIsolateTag).toHaveBeenCalledWith('Recipes');
    rerender(<SidePanel {...baseProps} onIsolateTag={onIsolateTag} isolatedTag="Recipes" />);
    fireEvent.click(screen.getByRole('button', { name: 'Recipes' }));
    expect(onIsolateTag).toHaveBeenCalledWith(null);
  });

  it('offers no layout sliders — the cloud sizes itself', () => {
    render(<SidePanel {...baseProps} />);
    expect(screen.queryByRole('slider')).toBeNull();
  });

  it('only offers ghosting when the filter actually excludes something', () => {
    // Unfiltered, every note is already on screen, so the toggle would visibly do
    // nothing — which reads as a broken control.
    const { rerender } = render(<SidePanel {...baseProps} canGhost={false} />);
    expect(screen.getByRole('checkbox', { name: /ghost/i })).toBeDisabled();

    rerender(<SidePanel {...baseProps} canGhost />);
    expect(screen.getByRole('checkbox', { name: /ghost/i })).not.toBeDisabled();
  });

  it('enables hiding for a selection or an isolated tag, but not for neither', () => {
    const onToggleHideUnfocused = vi.fn();
    const { rerender } = render(
      <SidePanel {...baseProps} onToggleHideUnfocused={onToggleHideUnfocused} />,
    );
    const toggle = () => screen.getByRole('checkbox', { name: /hide everything else/i });

    // Nothing focused: there is no "everything else" to hide.
    expect(toggle()).toBeDisabled();

    // A tag isolated from the legend is focus enough, with no note selected.
    rerender(
      <SidePanel
        {...baseProps}
        isolatedTag="Recipes"
        onToggleHideUnfocused={onToggleHideUnfocused}
      />,
    );
    expect(toggle()).not.toBeDisabled();

    rerender(<SidePanel {...selectedProps} onToggleHideUnfocused={onToggleHideUnfocused} />);
    expect(toggle()).not.toBeDisabled();
    fireEvent.click(toggle());
    expect(onToggleHideUnfocused).toHaveBeenCalled();
  });

  it('explains what is being hidden, naming the isolated tag', () => {
    const { rerender } = render(<SidePanel {...baseProps} isolatedTag="Recipes" hideUnfocused />);
    expect(screen.getByText(/only notes tagged Recipes/i)).toBeTruthy();

    // Selection outranks tag isolation, so the hint follows the selection.
    rerender(<SidePanel {...selectedProps} isolatedTag="Recipes" hideUnfocused />);
    expect(screen.getByText(/only this note and its connections/i)).toBeTruthy();
  });

  it('shows a connections error inline without hiding the rest of the panel', () => {
    render(<SidePanel {...selectedProps} connections={null} connectionsError="boom" />);
    expect(screen.getByText(/boom/)).toBeTruthy();
    expect(screen.getByText('My note')).toBeTruthy();
  });
});
