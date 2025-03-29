import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';

import { ChatMessage } from '@/components/Chat/ChatMessage';
import { ChatNotes } from '@/components/Chat/ChatNotes';
import { useChat } from '@/hooks/useChat';

import './styles.css';

interface ChatProps {
  query: string;
  onShowRelated: (content: string) => void;
}

export const Chat = ({ query, onShowRelated }: ChatProps) => {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { messages, isLoading, sendMessage, clearChat, stopGenerating, relevantNotes, modelName } =
    useChat();

  // Scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = useCallback(
    (e: FormEvent) => {
      e.preventDefault();
      if (!inputValue.trim() || isLoading) {
        return;
      }

      sendMessage(inputValue.trim());
      setInputValue('');
    },
    [inputValue, isLoading, sendMessage],
  );

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
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
        sendMessage(inputValue.trim());
        setInputValue('');
      }
    },
    [inputValue, isLoading, sendMessage],
  );

  return (
    <div className="chat-container">
      <div className="chat-header">
        <h2>
          <span className="material-icons">chat</span>
          AI Assistant
          {modelName && <span className="model-info">Using {modelName}</span>}
        </h2>
        <div className="chat-controls">
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
        <div className="chat-messages-container">
          <div className="chat-messages">
            {messages.length === 0 ? (
              <div className="empty-chat">
                <span className="material-icons">smart_toy</span>
                <p>Ask me anything about your notes!</p>
              </div>
            ) : (
              messages.map((message, index) => <ChatMessage key={index} message={message} />)
            )}
            <div ref={messagesEndRef} />
          </div>

          <form className="chat-input" onSubmit={handleSubmit}>
            <input
              type="text"
              value={inputValue}
              onChange={handleInputChange}
              onKeyDown={handleKeyDown}
              placeholder="Type your message..."
              disabled={isLoading}
            />
            <button type="submit" disabled={!inputValue.trim() || isLoading}>
              {isLoading ? (
                <span className="material-icons loading-icon">sync</span>
              ) : (
                <span className="material-icons">send</span>
              )}
            </button>
          </form>
        </div>

        <div className="notes-container">
          <ChatNotes notes={relevantNotes} query={query} onShowRelated={onShowRelated} />
        </div>
      </div>
    </div>
  );
};
