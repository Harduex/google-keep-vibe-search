import { memo, useState, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';

import type { ChatMessage as ChatMessageType } from '@/hooks/useChat';
import type { GroundedContext } from '@/types';
import { buildCitationNumberMap, parseCitations } from '@/utils/citationParser';

import { CitationInline } from './CitationInline';

import './styles.css';

interface ChatMessageProps {
  message: ChatMessageType;
  /** Legacy callback for old [Note #N] chips. */
  onCitationClick?: (noteNumber: number) => void;
  /** New: callback when a grounded citation is clicked. */
  onGroundedCitationClick?: (citationId: string) => void;
  /** Context items used for this conversation turn. */
  contextItems?: GroundedContext[];
}

export const ChatMessage = memo(
  ({ message, onCitationClick, onGroundedCitationClick, contextItems = [] }: ChatMessageProps) => {
    const { role, content, timestamp, citations, groundedCitations } = message;
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

    // Parse [citation:id] markers from processed content
    const parsedContent = useMemo(() => {
      if (role !== 'assistant' || !processedContent) {
        return null;
      }
      return parseCitations(processedContent, contextItems);
    }, [role, processedContent, contextItems]);

    const citationNumberMap = useMemo(() => {
      if (!parsedContent) {
        return new Map<string, number>();
      }
      return buildCitationNumberMap(parsedContent.citations);
    }, [parsedContent]);

    const toggleThinking = useCallback(() => {
      setIsThinkingExpanded(!isThinkingExpanded);
    }, [isThinkingExpanded]);

    const hasInlineCitations = parsedContent && parsedContent.citations.length > 0;

    // Render processed content with inline citations when available
    const renderContent = () => {
      if (!processedContent) {
        return null;
      }

      // If we have parsed inline citations, render segments
      if (hasInlineCitations && parsedContent) {
        return (
          <div className="message-text">
            {parsedContent.segments.map((segment, idx) => {
              if (segment.type === 'citation' && segment.citationId) {
                const citation = parsedContent.citations.find(
                  (c) => c.citation_id === segment.citationId,
                );
                const num = citationNumberMap.get(segment.citationId) ?? 0;
                if (citation && onGroundedCitationClick) {
                  return (
                    <CitationInline
                      key={`cit-${idx}`}
                      citationId={segment.citationId}
                      displayNumber={num}
                      citation={citation}
                      onCitationClick={onGroundedCitationClick}
                    />
                  );
                }
                // Fallback: render as superscript text
                return (
                  <sup key={`cit-${idx}`} className="citation-fallback">
                    [{num}]
                  </sup>
                );
              }

              // Text segment -- render through markdown
              return <ReactMarkdown key={`txt-${idx}`}>{segment.text}</ReactMarkdown>;
            })}
          </div>
        );
      }

      // Default: render as plain markdown (no inline citations)
      return (
        <div className="message-text">
          <ReactMarkdown>{processedContent}</ReactMarkdown>
        </div>
      );
    };

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

          {renderContent()}

          {/* Grounded citation summary chips */}
          {hasInlineCitations && parsedContent && (
            <div className="citations-section">
              <span className="citations-label">Sources:</span>
              {parsedContent.citations.map((c) => {
                const num = citationNumberMap.get(c.citation_id) ?? 0;
                return (
                  <button
                    key={c.citation_id}
                    className="citation-chip"
                    onClick={() => onGroundedCitationClick?.(c.citation_id)}
                    title={c.note_title || c.citation_id}
                  >
                    [{num}] {c.note_title || c.citation_id}
                  </button>
                );
              })}
            </div>
          )}

          {/* Legacy citations fallback */}
          {!hasInlineCitations && citations && citations.length > 0 && (
            <div className="citations-section">
              <span className="citations-label">Sources:</span>
              {citations.map((c) => (
                <button
                  key={c.note_id}
                  className="citation-chip"
                  onClick={() => onCitationClick?.(c.note_number)}
                  title={c.note_title}
                >
                  Note #{c.note_number}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  },
);
