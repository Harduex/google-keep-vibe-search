import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { ChatMessage as ChatMessageType } from '@/hooks/useChat';

import { ChatMessage } from '../ChatMessage';

describe('ChatMessage', () => {
  const baseUserMessage: ChatMessageType = {
    role: 'user',
    content: 'Hello, can you help me?',
    timestamp: Date.now(),
  };

  const baseAssistantMessage: ChatMessageType = {
    role: 'assistant',
    content: 'Of course! How can I assist you?',
    timestamp: Date.now(),
  };

  it('renders user message with correct sender label', () => {
    render(<ChatMessage message={baseUserMessage} />);
    expect(screen.getByText('You')).toBeInTheDocument();
  });

  it('renders assistant message with correct sender label', () => {
    render(<ChatMessage message={baseAssistantMessage} />);
    expect(screen.getByText('Assistant')).toBeInTheDocument();
  });

  it('renders message content', () => {
    render(<ChatMessage message={baseUserMessage} />);
    expect(screen.getByText('Hello, can you help me?')).toBeInTheDocument();
  });

  it('renders timestamp', () => {
    const msg: ChatMessageType = {
      ...baseUserMessage,
      timestamp: new Date('2024-01-15T14:30:00').getTime(),
    };
    render(<ChatMessage message={msg} />);
    // Should contain formatted time (various locale formats)
    const timeEl = document.querySelector('.message-time');
    expect(timeEl).toBeInTheDocument();
    expect(timeEl?.textContent).toBeTruthy();
  });

  it('renders citations when present', () => {
    const msg: ChatMessageType = {
      ...baseAssistantMessage,
      citations: [
        { note_number: 1, note_id: 'note-a', note_title: 'Project Plan' },
        { note_number: 3, note_id: 'note-c', note_title: 'Timeline' },
      ],
    };
    render(<ChatMessage message={msg} />);
    expect(screen.getByText('Sources:')).toBeInTheDocument();
    expect(screen.getByText('Note #1')).toBeInTheDocument();
    expect(screen.getByText('Note #3')).toBeInTheDocument();
  });

  it('calls onCitationClick when citation is clicked', () => {
    const handleClick = vi.fn();
    const msg: ChatMessageType = {
      ...baseAssistantMessage,
      citations: [{ note_number: 2, note_id: 'note-b', note_title: 'Budget' }],
    };
    render(<ChatMessage message={msg} onCitationClick={handleClick} />);
    fireEvent.click(screen.getByText('Note #2'));
    expect(handleClick).toHaveBeenCalledWith(2);
  });

  it('does not render citations section when no citations', () => {
    render(<ChatMessage message={baseAssistantMessage} />);
    expect(screen.queryByText('Sources:')).not.toBeInTheDocument();
  });

  it('renders thinking section toggle for assistant messages with think tags', () => {
    const msg: ChatMessageType = {
      role: 'assistant',
      content: '<think>Let me analyze this...</think>Here is my answer.',
      timestamp: Date.now(),
    };
    render(<ChatMessage message={msg} />);
    expect(screen.getByText('Show thinking')).toBeInTheDocument();
    expect(screen.getByText('Here is my answer.')).toBeInTheDocument();
  });

  it('expands thinking section on toggle click', () => {
    const msg: ChatMessageType = {
      role: 'assistant',
      content: '<think>Deep analysis here</think>The answer is 42.',
      timestamp: Date.now(),
    };
    render(<ChatMessage message={msg} />);
    fireEvent.click(screen.getByText('Show thinking'));
    expect(screen.getByText('Hide thinking')).toBeInTheDocument();
    expect(screen.getByText('Deep analysis here')).toBeInTheDocument();
  });

  it('does not render thinking section for user messages', () => {
    const msg: ChatMessageType = {
      role: 'user',
      content: '<think>This should not be treated as thinking</think>Regular text.',
    };
    render(<ChatMessage message={msg} />);
    expect(screen.queryByText('Show thinking')).not.toBeInTheDocument();
  });
});
