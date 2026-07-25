import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';

import { AgentSteps } from '@/components/Chat/AgentSteps';
import { ChatMessage } from '@/components/Chat/ChatMessage';
import { ChatNotes } from '@/components/Chat/ChatNotes';
import { ChatScope } from '@/components/Chat/ChatScope';
import { GroundingScore } from '@/components/Chat/GroundingScore';
import { SessionList } from '@/components/Chat/SessionList';
import { useChat } from '@/hooks/useChat';

import './styles.css';

interface ChatProps {
  query: string;
  onShowRelated: (content: string) => void;
}

export const Chat = ({ query, onShowRelated }: ChatProps) => {
  const [inputValue, setInputValue] = useState('');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const chatMessagesRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const {
    messages,
    isLoading,
    sendMessage,
    clearChat,
    stopGenerating,
    relevantNotes,
    conflicts,
    modelName,
    modelInfo,
    useNotesContext,
    toggleNotesContext,
    availableTags,
    selectedTags,
    setSelectedTags,
    dateRange,
    setDateRange,
    currentPhase,
    suggestions,
    agentSteps,
    groundingResult,
    // Session management
    sessionId,
    sessions,
    newChat,
    loadSession,
    deleteSession,
    renameSession,
  } = useChat();

  // Estimate token count for a text string (~4 chars per token)
  const estimateTokens = (text: string): number => {
    if (!text) {
      return 0;
    }
    return Math.ceil(text.length / 4);
  };

  const maxRecentMsgs = modelInfo?.chat_max_recent_messages || 6;
  const recentMessages = messages.slice(-maxRecentMsgs);
  const conversationTokens = recentMessages.reduce(
    (acc, msg) => acc + estimateTokens(msg.content),
    0,
  );

  const notesTokens = useNotesContext
    ? relevantNotes.reduce(
        (acc, note) => acc + estimateTokens(`${note.title || ''} ${note.content || ''}`),
        0,
      )
    : 0;

  const systemBaseTokens = 200;
  const totalInputTokens = conversationTokens + notesTokens + systemBaseTokens;
  const maxInputTokens = modelInfo?.max_input_tokens || 8192;
  const maxOutputTokens = modelInfo?.max_output_tokens || 2048;
  const remainingTokens = Math.max(0, maxInputTokens - totalInputTokens);
  const usagePct = Math.min(100, Math.round((totalInputTokens / maxInputTokens) * 100));
  const remainingPct = Math.max(0, 100 - usagePct);
  const maxNotesConfig = modelInfo?.chat_context_notes || 10;

  const userHasScrolledUpRef = useRef(false);

  const scrollToBottom = useCallback((smooth = true) => {
    messagesEndRef.current?.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto' });
  }, []);

  // Listen to scroll events: if user manually scrolls away from bottom,
  // immediately pause auto-scroll. Resume when user scrolls back to bottom.
  const handleScroll = useCallback(() => {
    const container = chatMessagesRef.current;
    if (!container) {
      return;
    }
    const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 40;
    if (isAtBottom) {
      userHasScrolledUpRef.current = false;
    } else {
      userHasScrolledUpRef.current = true;
    }
  }, []);

  // Smart auto-scroll: scroll to bottom while streaming ONLY IF user has not scrolled away
  useEffect(() => {
    if (!userHasScrolledUpRef.current) {
      scrollToBottom(!isLoading);
    }
  }, [messages, agentSteps, currentPhase, isLoading, scrollToBottom]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 150)}px`;
    }
  }, [inputValue]);

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      if (!inputValue.trim() || isLoading) {
        return;
      }

      userHasScrolledUpRef.current = false;
      sendMessage(inputValue.trim());
      setInputValue('');
      setTimeout(() => scrollToBottom(true), 50);
    },
    [inputValue, isLoading, sendMessage, scrollToBottom],
  );

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLTextAreaElement>) => {
    setInputValue(e.target.value);
  }, []);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      // Send message on Enter without shift key
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!inputValue.trim() || isLoading) {
          return;
        }
        userHasScrolledUpRef.current = false;
        sendMessage(inputValue.trim());
        setInputValue('');
        setTimeout(() => scrollToBottom(true), 50);
      }
    },
    [inputValue, isLoading, sendMessage, scrollToBottom],
  );

  const toggleSidebar = useCallback(() => {
    setSidebarOpen((prev) => !prev);
  }, []);

  const handleCitationClick = useCallback((noteNumber: number) => {
    const el = document.getElementById(`context-note-${noteNumber}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('citation-highlight');
      setTimeout(() => el.classList.remove('citation-highlight'), 2000);
    }
  }, []);

  const lastMessage = messages[messages.length - 1];
  const isLastMessageAssistant = lastMessage?.role === 'assistant';
  const previousMessages = isLastMessageAssistant ? messages.slice(0, -1) : messages;
  const activeAssistantMessage = isLastMessageAssistant ? lastMessage : null;

  return (
    <div className="chat-container">
      <div className="chat-header">
        <div className="header-title-area">
          <button
            className="sidebar-toggle-btn"
            onClick={toggleSidebar}
            title={sidebarOpen ? 'Hide sessions' : 'Show sessions'}
          >
            <span className="material-icons">{sidebarOpen ? 'menu_open' : 'menu'}</span>
          </button>
          <span className="material-icons chat-title-icon">chat</span>
          <span className="chat-title-text">AI Assistant</span>
          {modelName && <span className="model-tag-badge">{modelName}</span>}
        </div>

        <div className="chat-controls">
          <div
            className="context-usage-badge"
            title={`Model Context Window: ${maxInputTokens.toLocaleString()} tokens\nMax Output Limit: ${maxOutputTokens.toLocaleString()} tokens\n\nActive Context Breakdown:\n• Notes Context: ${relevantNotes.length} / ${maxNotesConfig} notes (~${notesTokens.toLocaleString()} tokens)\n• Message Window: ${recentMessages.length} msgs (~${conversationTokens.toLocaleString()} tokens)\n• System Base Prompt: ~${systemBaseTokens} tokens\n• Total Input Used: ~${totalInputTokens.toLocaleString()} tokens\n• Remaining Input Capacity: ~${remainingTokens.toLocaleString()} tokens (${remainingPct}% left)`}
          >
            <span className="material-icons context-icon">memory</span>
            <span className="context-text">
              Context: <strong>~{totalInputTokens.toLocaleString()}</strong> /{' '}
              {maxInputTokens.toLocaleString()} tokens
            </span>
            <div className="context-progress-bar">
              <div
                className={`context-progress-fill ${
                  usagePct > 85 ? 'danger' : usagePct > 65 ? 'warning' : 'normal'
                }`}
                style={{ width: `${Math.min(100, Math.max(4, usagePct))}%` }}
              />
            </div>
            <span className="context-remaining">({remainingPct}% left)</span>
          </div>
          {isLoading && (
            <button
              className="stop-button"
              onClick={stopGenerating}
              title="Stop answering"
              aria-label="Stop answering"
            >
              <span className="material-icons">stop</span>
              Stop Answering
            </button>
          )}
          <div className="notes-toggle">
            <label
              className="toggle-label"
              title={useNotesContext ? 'Notes context is enabled' : 'Notes context is disabled'}
            >
              <input
                type="checkbox"
                checked={useNotesContext}
                onChange={toggleNotesContext}
                disabled={isLoading}
              />
              <span className="toggle-slider"></span>
              <span className="toggle-text">
                <span className="material-icons">description</span>
                Use Notes Context
              </span>
            </label>
          </div>
          <button
            className="clear-button"
            onClick={clearChat}
            title="Clear chat"
            aria-label="Clear chat"
            disabled={messages.length === 0}
          >
            <span className="material-icons">delete</span>
            Clear Chat
          </button>
        </div>
      </div>

      <div className="chat-layout">
        {sidebarOpen && (
          <div className="sessions-sidebar">
            <SessionList
              sessions={sessions}
              activeSessionId={sessionId}
              onNewChat={newChat}
              onLoadSession={loadSession}
              onDeleteSession={deleteSession}
              onRenameSession={renameSession}
            />
          </div>
        )}

        <div className="chat-messages-container">
          <div className="chat-messages" ref={chatMessagesRef} onScroll={handleScroll}>
            {messages.length === 0 ? (
              <div className="empty-chat">
                <span className="material-icons">smart_toy</span>
                <p>Ask me anything about your notes!</p>
              </div>
            ) : (
              <>
                {previousMessages.map((message, index) => (
                  <ChatMessage
                    key={index}
                    message={message}
                    onCitationClick={handleCitationClick}
                  />
                ))}
                {agentSteps.length > 0 ? (
                  <AgentSteps steps={agentSteps} isActive={isLoading} />
                ) : currentPhase ? (
                  <div className="phase-indicator">
                    <span className="material-icons phase-icon">
                      {currentPhase === 'searching' ? 'search' : 'edit'}
                    </span>
                    <span className="phase-text">
                      {currentPhase === 'searching'
                        ? 'Searching your notes...'
                        : 'Generating response...'}
                    </span>
                  </div>
                ) : null}
                {activeAssistantMessage && (
                  <ChatMessage
                    key={messages.length - 1}
                    message={activeAssistantMessage}
                    onCitationClick={handleCitationClick}
                  />
                )}
              </>
            )}
            {groundingResult && !isLoading && <GroundingScore result={groundingResult} />}
            {suggestions.length > 0 && !isLoading && (
              <div className="suggestion-chips">
                <span className="suggestions-label">Follow-up:</span>
                {suggestions.map((q, i) => (
                  <button
                    key={i}
                    className="suggestion-chip"
                    onClick={() => sendMessage(q)}
                    disabled={isLoading}
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <form className="chat-input" onSubmit={handleSubmit}>
            {useNotesContext && (
              <ChatScope
                availableTags={availableTags}
                selectedTags={selectedTags}
                onSelectedTagsChange={setSelectedTags}
                dateRange={dateRange}
                onDateRangeChange={setDateRange}
                disabled={isLoading}
              />
            )}
            <div className="input-wrapper">
              <textarea
                id="chat-message-input"
                name="message"
                ref={textareaRef}
                value={inputValue}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                placeholder="Type your message... (Enter to send, Shift+Enter for new line)"
                disabled={isLoading}
                rows={1}
              />
              <button type="submit" disabled={!inputValue.trim() || isLoading}>
                {isLoading ? (
                  <span className="material-icons loading-icon">sync</span>
                ) : (
                  <span className="material-icons">send</span>
                )}
              </button>
            </div>
          </form>
        </div>

        <div className="notes-container">
          <ChatNotes
            notes={relevantNotes}
            conflicts={conflicts}
            query={query}
            onShowRelated={onShowRelated}
          />
        </div>
      </div>
    </div>
  );
};
