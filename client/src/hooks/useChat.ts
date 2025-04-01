import { useState, useEffect, useCallback, useRef } from 'react';

import { API_ROUTES } from '@/const';
import { Note } from '@/types';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: number;
}

interface StreamResponse {
  response: string;
  notes: Note[];
  error?: string;
}

export const useChat = () => {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [relevantNotes, setRelevantNotes] = useState<Note[]>([]);
  const [modelName, setModelName] = useState<string | null>(null);
  const [useNotesContext, setUseNotesContext] = useState<boolean>(true);

  const abortControllerRef = useRef<AbortController | null>(null);

  // Fetch the model name on mount
  useEffect(() => {
    const fetchModelInfo = async () => {
      try {
        const response = await fetch(API_ROUTES.CHAT_MODEL);
        const data = await response.json();
        setModelName(data.model);
      } catch (err) {
        // eslint-disable-next-line no-console
        console.error('Error fetching model info:', err);
      }
    };

    fetchModelInfo();
  }, []);

  const stopGenerating = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
      setIsLoading(false);
    }
  }, []);

  const sendMessage = useCallback(
    async (content: string) => {
      if (!content.trim()) {
        return;
      }

      // Add user message
      const userMessage: ChatMessage = {
        role: 'user',
        content,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, userMessage]);
      setIsLoading(true);
      setError(null);

      // Create a placeholder for the assistant's response with a guaranteed unique timestamp
      // Ensure it's different from the user message timestamp by adding 1ms
      const assistantMessageId = Date.now() + 1;
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: '',
        timestamp: assistantMessageId,
      };

      setMessages((prev) => [...prev, assistantMessage]);

      // Prepare request data
      const payload = {
        messages: [...messages, userMessage].map(({ role, content }) => ({ role, content })),
        stream: true,
        useNotesContext, // Include the context preference in the payload
      };

      // Stop any existing stream
      stopGenerating();

      // Create a new abort controller for this request
      abortControllerRef.current = new AbortController();

      try {
        // Start streaming request
        const response = await fetch(API_ROUTES.CHAT, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
          signal: abortControllerRef.current.signal,
        });

        if (!response.ok) {
          throw new Error(`HTTP error ${response.status}`);
        }

        const reader = response.body?.getReader();
        if (!reader) {
          throw new Error('ReadableStream not supported');
        }

        let accumulatedContent = '';
        const decoder = new TextDecoder();

        // Process the stream
        while (true) {
          const { done, value } = await reader.read();

          if (done) {
            break;
          }

          // Decode and handle the chunk
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n').filter((line) => line.trim());

          for (const line of lines) {
            try {
              const data: StreamResponse = JSON.parse(line);

              if (data.error) {
                setError(data.error);
                continue;
              }

              // Update the assistant's message, ensuring we only update assistant messages
              accumulatedContent = data.response;

              setMessages((prevMessages) =>
                prevMessages.map((msg) =>
                  msg.timestamp === assistantMessageId && msg.role === 'assistant'
                    ? { ...msg, content: accumulatedContent }
                    : msg,
                ),
              );

              // Update relevant notes if provided
              if (data.notes && data.notes.length > 0) {
                setRelevantNotes(data.notes);
              }
            } catch (e) {
              // eslint-disable-next-line no-console
              console.error('Error parsing stream chunk:', e, line);
            }
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setError(`Error: ${(err as Error).message}`);
          // eslint-disable-next-line no-console
          console.error('Chat error:', err);
        }
      } finally {
        abortControllerRef.current = null;
        setIsLoading(false);
      }
    },
    [messages, stopGenerating, useNotesContext],
  );

  const clearChat = useCallback(() => {
    stopGenerating();
    setMessages([]);
    setRelevantNotes([]);
    setError(null);
  }, [stopGenerating]);

  const toggleNotesContext = useCallback(() => {
    setUseNotesContext((prev) => !prev);
  }, []);

  return {
    messages,
    isLoading,
    error,
    relevantNotes,
    modelName,
    useNotesContext,
    sendMessage,
    clearChat,
    stopGenerating,
    toggleNotesContext,
  };
};
