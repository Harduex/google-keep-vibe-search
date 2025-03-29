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
    if (role !== 'assistant') {
      return {
        hasThinkingSection: false,
        processedContent: content,
        thinkingContent: '',
      };
    }

    // Check if we have a complete thinking section (both opening and closing tags)
    if (content.includes('<think>') && content.includes('</think>')) {
      // Extract thinking section with <think> tags
      const thinkRegex = /<think>([\s\S]*?)<\/think>/;
      const matches = content.match(thinkRegex);

      if (matches) {
        const thinkingContent = matches[1].trim();
        // Get everything after the last </think> tag
        const processedContent = content.substring(content.indexOf('</think>') + 8).trim();
        return { hasThinkingSection: true, processedContent, thinkingContent };
      }
    }
    // Check if we have only opening tag - still streaming the thinking section
    else if (content.includes('<think>') && !content.includes('</think>')) {
      // We're still in the thinking section, everything after <think> is thinking
      const thinkingStart = content.indexOf('<think>') + 7;
      const thinkingContent = content.substring(thinkingStart).trim();
      // No final answer yet since thinking is not complete
      return { hasThinkingSection: true, processedContent: '', thinkingContent };
    }

    // No thinking tags or malformed tags
    return {
      hasThinkingSection: false,
      processedContent: content,
      thinkingContent: '',
    };
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

        {processedContent && (
          <div className="message-text">
            <ReactMarkdown>{processedContent}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  );
});
