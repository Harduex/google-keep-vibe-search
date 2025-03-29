import { memo, useState, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';

import type { ChatMessage as ChatMessageType } from '@/hooks/useChat';

import './styles.css';

interface ChatMessageProps {
  message: ChatMessageType;
}

export const ChatMessage = memo(({ message }: ChatMessageProps) => {
  const { role, content, timestamp } = message;
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(false);

  const formattedTime = timestamp
    ? new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
    : '';

  // Process content to extract thinking sections
  const { hasThinkingSection, processedContent, thinkingContent } = useMemo(() => {
    if (role !== 'assistant' || !content.includes('<think>')) {
      return {
        hasThinkingSection: false,
        processedContent: content,
        thinkingContent: '',
      };
    }

    // Extract thinking section
    const thinkingMatch = content.match(/<think>([\s\S]*?)<\/think>/);
    if (!thinkingMatch) {
      return {
        hasThinkingSection: false,
        processedContent: content,
        thinkingContent: '',
      };
    }

    // Get thinking content and the rest of the message
    const thinkingContent = thinkingMatch[1].trim();
    const processedContent = content.replace(/<think>[\s\S]*?<\/think>/, '').trim();

    return { hasThinkingSection: true, processedContent, thinkingContent };
  }, [content, role]);

  const toggleThinking = useCallback(() => {
    setIsThinkingExpanded(!isThinkingExpanded);
  }, [isThinkingExpanded]);

  return (
    <div className={`chat-message ${role === 'assistant' ? 'assistant' : 'user'}`}>
      <div className="message-avatar">
        <span className="material-icons">{role === 'assistant' ? 'smart_toy' : 'person'}</span>
      </div>
      <div className="message-content">
        <div className="message-header">
          <span className="message-sender">{role === 'assistant' ? 'Assistant' : 'You'}</span>
          {timestamp && <span className="message-time">{formattedTime}</span>}
        </div>

        {hasThinkingSection && (
          <div className="thinking-section">
            <button
              className="thinking-toggle"
              onClick={toggleThinking}
              aria-expanded={isThinkingExpanded}
            >
              <span className="material-icons">
                {isThinkingExpanded ? 'expand_less' : 'expand_more'}
              </span>
              {isThinkingExpanded ? 'Hide thinking' : 'Show thinking'}
            </button>

            {isThinkingExpanded && (
              <div className="thinking-content">
                <ReactMarkdown>{thinkingContent}</ReactMarkdown>
              </div>
            )}
          </div>
        )}

        <div className="message-text">
          <ReactMarkdown>{processedContent}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
});
