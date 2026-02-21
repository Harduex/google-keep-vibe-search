import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChatSessionSummary } from '@/types';

import { SessionList } from '../SessionList';

const mockSessions: ChatSessionSummary[] = [
  { id: 'session-1', title: 'First Chat', message_count: 5, updated_at: new Date().toISOString() },
  {
    id: 'session-2',
    title: 'Second Chat',
    message_count: 3,
    updated_at: new Date(Date.now() - 86400000).toISOString(),
  },
  {
    id: 'session-3',
    title: 'Old Chat',
    message_count: 1,
    updated_at: new Date(Date.now() - 86400000 * 5).toISOString(),
  },
];

describe('SessionList', () => {
  const defaultProps = {
    sessions: mockSessions,
    activeSessionId: 'session-1',
    onNewChat: vi.fn(),
    onLoadSession: vi.fn(),
    onDeleteSession: vi.fn(),
    onRenameSession: vi.fn(),
  };

  it('renders session titles', () => {
    render(<SessionList {...defaultProps} />);
    expect(screen.getByText('First Chat')).toBeInTheDocument();
    expect(screen.getByText('Second Chat')).toBeInTheDocument();
    expect(screen.getByText('Old Chat')).toBeInTheDocument();
  });

  it('renders new chat button', () => {
    render(<SessionList {...defaultProps} />);
    expect(screen.getByText('New Chat')).toBeInTheDocument();
  });

  it('calls onNewChat when button clicked', () => {
    const onNewChat = vi.fn();
    render(<SessionList {...defaultProps} onNewChat={onNewChat} />);
    fireEvent.click(screen.getByText('New Chat'));
    expect(onNewChat).toHaveBeenCalledOnce();
  });

  it('calls onLoadSession when session clicked', () => {
    const onLoadSession = vi.fn();
    render(<SessionList {...defaultProps} onLoadSession={onLoadSession} />);
    fireEvent.click(screen.getByText('Second Chat'));
    expect(onLoadSession).toHaveBeenCalledWith('session-2');
  });

  it('highlights active session', () => {
    render(<SessionList {...defaultProps} />);
    const activeItem = screen.getByText('First Chat').closest('.session-item');
    expect(activeItem).toHaveClass('active');
  });

  it('shows empty state when no sessions', () => {
    render(<SessionList {...defaultProps} sessions={[]} />);
    expect(screen.getByText('No conversations yet')).toBeInTheDocument();
  });

  it('shows message count for each session', () => {
    render(<SessionList {...defaultProps} />);
    expect(screen.getByText(/5 msgs/)).toBeInTheDocument();
    expect(screen.getByText(/3 msgs/)).toBeInTheDocument();
    expect(screen.getByText(/1 msgs/)).toBeInTheDocument();
  });

  it('shows relative date for sessions', () => {
    render(<SessionList {...defaultProps} />);
    expect(screen.getByText(/Today/)).toBeInTheDocument();
    expect(screen.getByText(/Yesterday/)).toBeInTheDocument();
  });
});
