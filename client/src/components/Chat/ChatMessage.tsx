import { memo, useState, useMemo, useCallback } from 'react';
import ReactMarkdown from 'react-markdown';

import type { ChatMessage as ChatMessageType } from '@/hooks/useChat';

import './styles.css';

interface ChatMessageProps {
  message: ChatMessageType;
  onCitationClick?: (noteNumber: number) => void;
}

export const ChatMessage = memo(({ message, onCitationClick }: ChatMessageProps) => {
  const { role, content, timestamp, citations } = message;
  const [isThinkingExpanded, setIsThinkingExpanded] = useState(false);
  const [copied, setCopied] = useState(false);

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
    setIsThinkingExpanded((prev) => !prev);
  }, []);

  const handleCopy = useCallback(async () => {
    if (!processedContent || copied) {
      return;
    }
    try {
      await navigator.clipboard.writeText(processedContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = processedContent;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  }, [processedContent, copied]);

  const markdownComponents = useMemo(
    () => ({
      code({ className, children, ...props }: React.ComponentPropsWithoutRef<'code'>) {
        const match = /language-(\w+)/.exec(className || '');
        const isInline = !match && !String(children).includes('\n');
        return isInline ? (
          <code className="inline-code" {...props}>
            {children}
          </code>
        ) : (
          <div className="code-block-wrapper">
            {match && <div className="code-block-header">{match[1]}</div>}
            <pre className="code-block">
              <code className={className} {...props}>
                {children}
              </code>
            </pre>
          </div>
        );
      },
      a({ href, children }: React.ComponentPropsWithoutRef<'a'>) {
        return (
          <a href={href} target="_blank" rel="noopener noreferrer" className="markdown-link">
            {children}
          </a>
        );
      },
      blockquote({ children }: React.ComponentPropsWithoutRef<'blockquote'>) {
        return <blockquote className="markdown-blockquote">{children}</blockquote>;
      },
      table({ children }: React.ComponentPropsWithoutRef<'table'>) {
        return (
          <div className="table-container">
            <table className="markdown-table">{children}</table>
          </div>
        );
      },
    }),
    [],
  );

  return (
    <div className={`chat-message ${role === 'assistant' ? 'assistant' : 'user'}`}>
      <div className="message-avatar">
        <span className="material-icons">{role === 'assistant' ? 'smart_toy' : 'person'}</span>
      </div>
      <div className="message-content">
        <div className="message-header">
          <span className="message-sender">{role === 'assistant' ? 'Assistant' : 'You'}</span>
          <div className="message-header-actions">
            {timestamp && <span className="message-time">{formattedTime}</span>}
            {role === 'assistant' && processedContent && (
              <button
                className={`copy-message-btn${copied ? ' copied' : ''}`}
                onClick={handleCopy}
                title={copied ? 'Copied!' : 'Copy response'}
                aria-label={copied ? 'Copied to clipboard' : 'Copy response to clipboard'}
              >
                <span className="material-icons">{copied ? 'check' : 'content_copy'}</span>
              </button>
            )}
          </div>
        </div>

        {hasThinkingSection && (
          <div className="thinking-section">
            <button
              className="thinking-toggle"
              onClick={toggleThinking}
              aria-expanded={isThinkingExpanded}
            >
              <span className="material-icons thinking-icon">psychology</span>
              <span className="thinking-toggle-text">
                {isThinkingExpanded ? 'Hide thinking' : 'Show thinking'}
              </span>
              <span className="material-icons toggle-arrow">
                {isThinkingExpanded ? 'expand_less' : 'expand_more'}
              </span>
            </button>

            {isThinkingExpanded && (
              <div className="thinking-content">
                <ReactMarkdown components={markdownComponents}>{thinkingContent}</ReactMarkdown>
              </div>
            )}
          </div>
        )}

        {processedContent && (
          <div className="message-text">
            <ReactMarkdown components={markdownComponents}>{processedContent}</ReactMarkdown>
          </div>
        )}

        {citations && citations.length > 0 && (
          <div className="citations-section">
            <span className="citations-label">Sources:</span>
            {citations.map((c) => (
              <button
                key={c.note_id}
                className={`citation-chip ${c.verdict ? `citation-${c.verdict}` : ''}`}
                onClick={() => onCitationClick?.(c.note_number)}
                title={
                  c.verdict
                    ? `${c.note_title} — ${c.verdict}${c.support_score !== undefined ? ` (${Math.round(c.support_score * 100)}%)` : ''}`
                    : c.note_title
                }
              >
                {c.verdict === 'supported' && (
                  <span className="material-icons citation-icon">check_circle</span>
                )}
                {c.verdict === 'contradicted' && (
                  <span className="material-icons citation-icon">cancel</span>
                )}
                {c.verdict === 'neutral' && (
                  <span className="material-icons citation-icon">help</span>
                )}
                Note #{c.note_number}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
});
