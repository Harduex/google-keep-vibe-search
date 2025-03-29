import { useState, useCallback, useEffect } from 'react';

import { API_ROUTES } from '@/const';
import { useError } from '@/hooks/useError';
import { Note } from '@/types';

export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: number;
}

interface UseChatResult {
  messages: ChatMessage[];
  isLoading: boolean;
  relevantNotes: Note[];
  modelName: string;
  sendMessage: (content: string) => Promise<void>;
  clearChat: () => void;
  error: string | null;
}

export const useChat = (): UseChatResult => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [relevantNotes, setRelevantNotes] = useState<Note[]>([]);
  const [modelName, setModelName] = useState<string>('');
  const { error, handleError, clearError } = useError();

  // Fetch the model name when the hook is initialized
  useEffect(() => {
    const fetchModelName = async () => {
      try {
        const response = await fetch(API_ROUTES.CHAT_MODEL);
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const data = await response.json();
        setModelName(data.model || 'Unknown');
      } catch (err) {
        handleError(err);
      }
    };

    fetchModelName();
  }, [handleError]);

  const sendMessage = useCallback(
    async (content: string) => {
      try {
        setIsLoading(true);
        clearError();

        // Add the user message to the chat
        const userMessage: ChatMessage = {
          role: 'user',
          content,
          timestamp: Date.now(),
        };

        setMessages((prevMessages) => [...prevMessages, userMessage]);

        // Prepare the messages payload for the API
        const messagesPayload = [...messages, userMessage].map(({ role, content }) => ({
          role,
          content,
        }));

        const response = await fetch(API_ROUTES.CHAT, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            messages: messagesPayload,
            stream: false,
          }),
        });

        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Add the assistant's response to the chat
        const assistantMessage: ChatMessage = {
          role: 'assistant',
          content: data.response,
          timestamp: Date.now(),
        };

        setMessages((prevMessages) => [...prevMessages, assistantMessage]);
        setRelevantNotes(data.notes || []);
      } catch (err) {
        handleError(err);
      } finally {
        setIsLoading(false);
      }
    },
    [messages, clearError, handleError],
  );

  const clearChat = useCallback(() => {
    setMessages([]);
    setRelevantNotes([]);
    clearError();
  }, [clearError]);

  return {
    messages,
    isLoading,
    relevantNotes,
    modelName,
    sendMessage,
    clearChat,
    error,
  };
};
